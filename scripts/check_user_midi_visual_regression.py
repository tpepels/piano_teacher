#!/usr/bin/env python3
"""Compare real MIDI imports against *original Verovio* and Godot's actual strip.

Nothing in midi/ is regenerated or altered. The baseline is the rasterization
of the original Verovio SVG for exactly the same lesson/hand. Godot then reads
those exact PNG bytes, builds the user-facing score strip and exports its tiles.

Usage:
  .venv/bin/python scripts/check_user_midi_visual_regression.py
  .venv/bin/python scripts/check_user_midi_visual_regression.py --only Ala
  .venv/bin/python scripts/check_user_midi_visual_regression.py --out results/midi-visual
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback

from PIL import Image, ImageChops, ImageDraw, ImageFont

from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.music import Phrase
from piano_teacher.raster import rasterize_score
from piano_teacher.score import import_piece, render_layout


ROOT = Path(__file__).resolve().parents[1]
MIDI_DIR = ROOT / "midi"
# Explicit manifest: a rename or deletion must fail, not silently remove a test.
CASES = (
    ("Ala_–_Joep_Beving.midi", "left"),
    ("Bill_Evans_on_Autunm_Leaves_From_the_Album_Portrait_in_Jazz.midi", "right"),
    ("Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", "right"),
    ("Danny_Boy(Bill_Evans_Ver_).midi", "both"),
    ("Merry-Go-Round-of-Life.midi", "both"),
    ("Peace_Piece_-_Bill_Evans_(Piano_Solo).midi", "both"),
    ("Waltz_for_Debby.midi", "both"),
)


def _name(filename: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", Path(filename).stem).strip("-").lower()


def source_exercise(filename: str, hand: str, bars: int = 2):
    """Use original source measures at the application's 40% practice tempo."""
    piece, _ = import_piece(MIDI_DIR / filename)
    assert len(piece.bar_boundaries) >= bars + 1, (
        f"{filename}: missing requested {bars}-bar source grid"
    )
    end = piece.bar_boundaries[bars]
    notes = tuple(n for n in piece.notes if 0 <= n.start < end)
    assert notes, f"{filename}: no notes in the first {bars} measures"
    phrase = Phrase(1, 1, bars, 0, end, notes)
    exercise = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
    )
    # Matches e.g. Ala 44/110, Autumn Leaves 76/190, Chopin 24/60.
    bpm = max(1, round(piece.bpm * .4))
    # Match PracticeEngine.engraving(): only compact exercises use one
    # Verovio system. Longer real MIDI passages use the legacy multipage
    # renderer and *must* exercise the production strip's warp/join path.
    compact_exercise = bars <= 12 and end <= 48
    engraving = render_layout(exercise, 1, bars, hand,
                              total_beats=end, bpm=bpm,
                              continuous=compact_exercise)
    if not compact_exercise:
        assert not engraving.layout["continuous_score"], (
            "Long MIDI regression unexpectedly bypassed the production strip"
        )
    require_lesson_alignment(phrase, engraving.layout, hand)
    assert len(engraving.pages) == int(engraving.layout["pages"])
    if bars >= 13 and filename.startswith("Chopin"):
        safe_headers = engraving.layout["strip_trim_safe_starts"]
        assert 6.5 in safe_headers and 0.5 not in safe_headers, (
            "A genuine 1/8 -> 12/8 change must stay engraved, while later "
            "printed-system clefs must not reappear in the continuous strip"
        )
    assert len(engraving.layout["notes"]) == len(exercise.note_bindings), (
        f"{filename}: Verovio dropped or duplicated a source-bound note"
    )
    return piece, phrase, exercise, engraving, bpm


def check_native_ink(source_dir: Path, strip_dir: Path, report: dict) -> dict:
    """Original Verovio alpha must survive native Godot cropping pixel-for-pixel.

    ScoreStrip intentionally removes *isolated horizontal staff rules* to draw
    an unbroken grand staff. Ignore only a narrow band around those rules.
    Noteheads, accidentals, stems, beams, clefs, rests, dots and time signatures
    everywhere else must remain original Verovio ink.
    """
    native = report["cases"]["native"]
    production = report["cases"]["production"]
    assert len(native["notes"]) == report["source_note_count"]
    assert {n["id"] for n in native["notes"]} == {n["id"] for n in production["notes"]}
    tested_pixels = 0
    differences = []
    for index, info in enumerate(native["tiles"]):
        page = Image.open(source_dir / f"page-{info['page']}.png").convert("RGBA")
        x, y, w, h = info["crop"]
        source = page.crop((x, y, x + w, y + h)).getchannel("A")
        with Image.open(strip_dir / info["file"]) as image:
            output = image.convert("RGBA").getchannel("A")
        assert source.size == output.size, (
            f"Native Verovio glyph stretched at tile {index}: {source.size} != {output.size}"
        )
        delta = ImageChops.difference(source, output)
        draw = ImageDraw.Draw(delta)
        for row in info["staff_rows"]:
            cy = round(row)
            draw.rectangle((0, cy - 4, w, cy + 4), fill=0)
        # ImageTexture's LA8 conversion may quantize alpha by one level.
        histogram = delta.histogram()
        changed = sum(histogram[3:])
        tested_pixels += w * h - min(h, len(info["staff_rows"]) * 9) * w
        differences.append({"tile": index, "mismatched_pixels": changed,
                            "max_alpha_error": delta.getextrema()[1]})
        assert changed == 0, (
            f"Native strip changed {changed} genuine Verovio ink pixels on tile "
            f"{index}, away from isolated staff rules"
        )
        if report["continuous_score"]:
            other_info = production["tiles"][index]
            with Image.open(strip_dir / other_info["file"]) as image:
                other = image.convert("RGBA").getchannel("A")
            assert source.size == other.size, (
                "Continuous practice must not stretch native Verovio glyphs"
            )
            assert ImageChops.difference(output, other).getbbox() is None, (
                "Production changed real Verovio notes/clefs/accidentals "
                "relative to the native baseline"
            )
    return {"verified_non_staff_pixels": tested_pixels, "tiles": differences}


def _ink_panel(images: list[tuple[Image.Image, tuple[float, float]]],
               canvas_width: float, canvas_height: float, title: str,
               rail_rows: list[float] | None = None) -> Image.Image:
    """Make a human-readable comparison, not a pixel-difference pass condition."""
    color = (26, 43, 38)
    width, height = 1480, 340
    panel = Image.new("RGB", (width, height), color)
    pen = ImageDraw.Draw(panel)
    pen.text((14, 12), title, fill=(183, 207, 192))
    if canvas_width <= 0 or canvas_height <= 0:
        return panel
    scale = min(1430 / canvas_width, 275 / canvas_height)
    x_pad = 22
    y_pad = 45 + max(0, (275 - canvas_height * scale) / 2)
    # The real Godot renderer removes isolated staff-rule ink from every
    # tile, then draws one continuous grand staff underneath the sprites.
    # Comparison screenshots must include that layer or falsely show a
    # score without a notenbalk (the former misleading comparison bug).
    for rail in rail_rows or []:
        py = round(y_pad + rail * scale)
        pen.line(((x_pad, py), (round(x_pad + canvas_width * scale), py)),
                 fill=(121, 154, 143), width=1)
    for img, (x, y) in images:
        pix = img.convert("RGBA")
        # Treat source ink's opacity as the compositing mask, so both
        # reference SVG and Godot tiles are shown in identical light ink.
        mask = pix.getchannel("A")
        new_size = (max(1, round(pix.width * scale)),
                    max(1, round(pix.height * scale)))
        mask = mask.resize(new_size, Image.Resampling.LANCZOS)
        layer = Image.new("RGB", new_size, (229, 242, 233))
        panel.paste(layer, (round(x_pad + x * scale), round(y_pad + y * scale)), mask)
    return panel


def write_comparison(input_dir: Path, output_dir: Path, report: dict,
                     label: str) -> None:
    original_images = []
    for page in range(len(list(input_dir.glob("page-*.png")))):
        img = Image.open(input_dir / f"page-{page}.png")
        original_images.append(img.copy())
        img.close()
    # Original SVG raster page; for multi-system scores all pages are
    # preserved separately alongside their Godot-rendered tiles.
    src = original_images[0]
    ref_panel = _ink_panel([(src, (0, 0))], src.width, src.height,
                           f"ORIGINAL VEROVIO SVG  ·  {label}")
    strip = report["cases"]["production"]
    render_tiles = []
    for info in strip["tiles"]:
        img = Image.open(output_dir / info["file"])
        render_tiles.append((img.copy(), tuple(info["rect"][:2])))
        img.close()
    rails = []
    if strip["tiles"]:
        first = strip["tiles"][0]
        rails = [first["rect"][1] + float(row) for row in first["staff_rows"]]
    # Do not shrink an entire 60,000px score into a 1,480px thumbnail.
    # A pianist sees a local camera window, not the full scroll strip;
    # compare a readable initial window while keeping every tile as
    # machine-readable artifact for later offscreen/seek regression.
    visible_width = min(float(strip["width"]), 3600.0)
    dst_panel = _ink_panel(render_tiles, visible_width, strip["height"],
                           f"GODOT SCORE VIEWPORT, FIRST {visible_width:.0f} SOURCE PX  ·  {label}",
                           rail_rows=rails)
    comparison = Image.new("RGB", (1480, 700), (26, 43, 38))
    comparison.paste(ref_panel, (0, 0))
    comparison.paste(dst_panel, (0, 354))
    comparison.save(output_dir / "comparison.png")


def run_one(filename: str, hand: str, out: Path, godot: str,
            bars: int = 2) -> dict:
    identifier = _name(filename) + "-" + hand + f"-{bars}bars"
    folder = out / identifier
    source_dir, strip_dir = folder / "verovio", folder / "godot"
    source_dir.mkdir(parents=True, exist_ok=True)
    strip_dir.mkdir(parents=True, exist_ok=True)
    piece, phrase, exercise, engraving, bpm = source_exercise(filename, hand, bars)
    (source_dir / "score.musicxml").write_text(exercise.musicxml)
    (source_dir / "layout.json").write_text(
        json.dumps(engraving.layout, indent=2) + "\n")
    for page, svg in enumerate(engraving.pages):
        (source_dir / f"page-{page}.svg").write_text(svg)
        (source_dir / f"page-{page}.png").write_bytes(
            rasterize_score(svg, width=3000))
    command = [godot, "--headless", "--path", str(ROOT / "godot"),
               "--script", str(ROOT / "tests/godot/user_midi_visual_regression.gd"),
               "--", str(source_dir), str(strip_dir)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=150)
    (folder / "godot.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, f"{filename}: Godot failed: {result.stdout} {result.stderr}"
    assert "USER_MIDI_VISUAL_FAILURES:0" in result.stdout, result.stdout + result.stderr
    report = json.loads((strip_dir / "godot-strip-report.json").read_text())
    if bars >= 13 and filename.startswith("Chopin"):
        trims = [tile["trimmed_header"] for tile in report["cases"]["production"]["tiles"]]
        assert len(trims) >= 3 and not trims[1] and trims[2], (
            "Preserve the real 12/8 meter change, but remove duplicated "
            "clefs at the next unchanged Verovio system start"
        )
    pixels = check_native_ink(source_dir, strip_dir, report)
    write_comparison(source_dir, strip_dir, report, f"{Path(filename).stem} / {hand}")
    return {"file": filename, "hand": hand, "bars": bars, "bpm": bpm,
            "source_notes": len(phrase.notes), "engraved_glyphs": len(engraving.layout["notes"]),
            "pages": len(engraving.pages), "continuous": report["continuous_score"],
            "pixels": pixels,
            "comparison": str((strip_dir / "comparison.png").relative_to(out))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/tmp/piano-user-midi-visual"))
    parser.add_argument("--only", help="Case-insensitive substring in the MIDI filename")
    args = parser.parse_args(argv)
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        parser.error("Godot 4 executable is required for actual strip regression")
    cases = [(f, h, 2) for f, h in CASES if not args.only or
             args.only.casefold() in f.casefold()]
    # A 2-bar compact system cannot exercise the older printed-system
    # stitching/warping path. Add deliberately non-compact 13-bar passages
    # for the three MIDI files in the reported visual regressions.
    cases += [(f, h, 13) for f, h in CASES[:3] if not args.only or
              args.only.casefold() in f.casefold()]
    if not cases:
        parser.error("No MIDI cases match --only")
    args.out.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    for file, hand, bars in cases:
        try:
            info = run_one(file, hand, args.out, godot, bars)
            results.append(info)
            print(f"PASS {file} ({bars} bars): {info['source_notes']} notes; "
                  f"{info['pixels']['verified_non_staff_pixels']} pixels checked",
                  flush=True)
        except Exception as exc:
            errors.append({"file": file, "bars": bars, "error": str(exc),
                           "traceback": traceback.format_exc()})
            print(f"FAIL {file} ({bars} bars): {exc}", file=sys.stderr, flush=True)
    (args.out / "report.json").write_text(json.dumps(
        {"passed": len(results), "failed": len(errors),
         "results": results, "failures": errors}, indent=2) + "\n")
    print(f"Visual regression: {len(results)} passed, {len(errors)} failed. "
          f"Evidence: {args.out.resolve()}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

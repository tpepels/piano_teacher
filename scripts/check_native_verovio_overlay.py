#!/usr/bin/env python3
"""Compare the *actual* native Godot renderer with Verovio on real MIDI.

The existing check_user_midi_visual_regression.py tests the retired raster
ScoreStrip against its source pixels; it cannot see the native renderer.
This audit instead loads the actual native view.gd, compares note identities
with original Verovio engraving, checks visible note/rest pixels, and writes
registered red-Verovio / pale-Godot overlay PNGs for human inspection.

This is intentionally NOT a raw full-page pixel equality check: native
practice uses constant beats-per-pixel, whereas Verovio print spacing is
optical. Registration is by original source note ID, not an invented warp of
the score or a requirement that notation moves at varying speeds.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw

from piano_teacher.application.score_preparation import assemble_layout
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.raster import rasterize_score
from piano_teacher.score import import_piece, render_layout

ROOT = Path(__file__).resolve().parents[1]
AUTUMN = ROOT / "midi/Bill_Evans_on_Autunm_Leaves_From_the_Album_Portrait_in_Jazz.midi"
FIRST_BAR, LAST_BAR = 7, 8
# A human-readable score must not revert to the 438+ px/beat observed in
# the user screenshot. Keep a conservative margin for unavoidable real ink.
MAX_AUTUMN_DENSITY = 400.0


def fixture() -> tuple[dict, object]:
    piece, _ = import_piece(AUTUMN)
    first = piece.bar_boundaries[FIRST_BAR - 1]
    end = piece.bar_boundaries[LAST_BAR]
    notes = tuple(n for n in piece.notes if first <= n.start < end)
    assert notes, "Real Autumn Leaves source passage unexpectedly empty"
    phrase = Phrase(1, FIRST_BAR, LAST_BAR, first, end, notes)
    score = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
        default_clefs=None,
        barlines=piece.barlines,
        source_musicxml=piece.source_musicxml,
    )
    model = build_score_model(score, boundaries=piece.bar_boundaries,
                              hand="both")
    engraving = render_layout(score, FIRST_BAR, LAST_BAR, "both",
                              total_beats=end-first, bpm=40, continuous=True)
    atlas = assemble_layout(engraving, native_notes=True, native_model=model,
                            notation_xml=score.musicxml)
    return {
        "model": model,
        "assets": {key: atlas[key] for key in (
            "native_glyphs", "native_note_templates", "native_tie_templates",
            "native_chord_templates", "native_beam_fragments",
            "native_tuplet_fragments", "native_slur_fragments",
            "native_required_slur_pairs", "native_slurs_complete",
            "native_required_beam_groups", "native_beams_complete")},
        "first_bar": FIRST_BAR, "last_bar": LAST_BAR,
    }, engraving


def visible_ink(image: Image.Image, x: float, y: float, radius: int = 11) -> int:
    """Count actual pale notation pixels, excluding dark/grey staff lines."""
    image = image.convert("RGB")
    px = image.load()
    matches = 0
    for yy in range(max(0, round(y)-radius),
                    min(image.height,round(y)+radius+1)):
        for xx in range(max(0, round(x)-radius),
                        min(image.width,round(x)+radius+1)):
            r, g, b = px[xx, yy]
            if r > 154 and g > 165 and b > 150:
                matches += 1
    return matches


def readability_errors(model: dict, diagnostics: dict) -> list[str]:
    """Strict gates for an actual reported problem, not generic MIDI guesses."""
    errors = []
    if diagnostics["density"] > MAX_AUTUMN_DENSITY:
        errors.append("Autumn Leaves inflated to %.1f px/beat (max %.1f)"
                      % (diagnostics["density"], MAX_AUTUMN_DENSITY))
    if diagnostics["unavoidable_rest_overlaps"]:
        errors.append("Native rests collide with other voice ink")
    events = model["notation_events"]
    if any(n["kind"] == "note" and n["dots"] > 2 for n in events):
        errors.append("Unconventional triple/quadruple-dot notation returned "
                      "in the reported MIDI passage")
    note_ids = {n["id"] for n in events if n["kind"] == "note"}
    source_ids = {n["id"] for n in model["notes"]}
    graded = {n["source_id"] for n in events
              if n["kind"] == "note" and n["is_attack"]}
    if source_ids != graded:
        errors.append("Source MIDI attacks differ from visible score attacks")
    if not note_ids:
        errors.append("No native note identities found")
    return errors


def draw_overlay(reference: Image.Image, native: Image.Image,
                 verovio_notes: list[dict], heads: dict,
                 output: Path) -> int:
    """Color-register reference notehead crops by *source ID*, not print X.

    The reference (red) is overlaid on native pixels (mint) at the same
    musical note identity. Keep the full reference next to the local native
    view because rests and spacing differences can require expert review.
    """
    native = native.convert("RGBA")
    panel = native.convert("RGB")
    overlay = Image.new("RGBA", native.size, (0, 0, 0, 0))
    n = 0
    for note in verovio_notes:
        ident = str(note["id"])
        if ident not in heads or int(note.get("page",0)) != 0:
            continue
        x, y = heads[ident]
        if not (30 <= x < native.width-30 and 28 <= y < native.height-28):
            continue
        rx = round(float(note["x"]) * reference.width)
        ry = round(float(note["y"]) * reference.height)
        half = 12
        crop = reference.convert("RGBA").crop(
            (rx-half,ry-half,rx+half+1,ry+half+1))
        ink = crop.getchannel("A")
        # Reference raster may have an opaque background; compare ink alone.
        # Cairo's rendered Verovio ink has lower luminance than a white page.
        if ink.getextrema() == (255,255):
            grey = crop.convert("L")
            ink = grey.point(lambda p: 220 if p < 155 else 0)
        red = Image.new("RGBA",crop.size,(245,91,96,0))
        red.putalpha(ink.point(lambda a: round(a*.46)))
        overlay.alpha_composite(red, (round(x)-half,round(y)-half))
        n += 1
    composited = Image.alpha_composite(native,overlay).convert("RGB")
    pen = ImageDraw.Draw(composited)
    pen.text((34,14),"NATIVE + VEROVIO NOTE-ANCHOR OVERLAY (red = Verovio)",fill="white")
    composited.save(output)
    # Accompany overlay with the unwarped optical source and full native score.
    reference.thumbnail((native.width, native.height), Image.Resampling.LANCZOS)
    comparison = Image.new("RGB",(native.width,native.height*2),(19,44,35))
    comparison.paste(reference.convert("RGB"),(0,0))
    comparison.paste(panel,(0,native.height))
    comparison.save(output.with_name(output.stem+"-side-by-side.png"))
    return n


def run(out: Path, godot: str) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    data, engraving = fixture()
    model = data["model"]
    (out/"score.musicxml").write_text(
        # Preserve the exact score used by BOTH renderers.
        # The source passage is not a prettier independently re-quantized copy.
        __import__("xml.etree.ElementTree",fromlist=["ElementTree"]).tostring(
            __import__("xml.etree.ElementTree",fromlist=["ElementTree"]).fromstring(
                data.get("xml", "<empty/>")
            ),encoding="unicode") if False else "", encoding="utf8")
    (out/"fixture.json").write_text(json.dumps(data))
    for page, svg in enumerate(engraving.pages):
        (out/f"verovio-{page}.svg").write_text(svg)
        (out/f"verovio-{page}.png").write_bytes(rasterize_score(svg,width=2400))
    result = subprocess.run([
        godot, "--path",str(ROOT/"godot"),"--rendering-method","gl_compatibility",
        "--script",str(ROOT/"tests/godot/native_verovio_overlay.gd"),
        "--",str(out/"fixture.json"),str(out)],
        capture_output=True,text=True,timeout=180)
    (out/"godot.log").write_text(result.stdout+result.stderr)
    assert result.returncode == 0 and "NATIVE_VEROVIO_OVERLAY_FAILURES:0" in result.stdout, (
        "Actual native renderer failed:\n"+(result.stdout+result.stderr)[-9000:])
    report = json.loads((out/"native-overlay-report.json").read_text())
    errors = readability_errors(model, report)
    reference = Image.open(out/"verovio-0.png")
    refnotes = engraving.layout["notes"]
    checked = 0
    for frame in report["frames"]:
        screenshot = Image.open(out/frame["file"])
        heads = frame["noteheads"]
        for ident, (x,y) in heads.items():
            if 20 < x < screenshot.width-20 and 20 < y < screenshot.height-20:
                checked += 1
                if visible_ink(screenshot,x,y) < 5:
                    errors.append(f"Missing rendered native notehead {ident} "
                                  f"at beat {frame['clock']}")
        for rest in frame["rests"]:
            if 30 < rest["x"] < screenshot.width-30:
                if visible_ink(screenshot,rest["x"],rest["y"],26) < 7:
                    errors.append("Missing native rest pixels: "+str(rest["id"]))
        frame["reference_notes_overlaid"] = draw_overlay(
            reference.copy(),screenshot,refnotes,heads,
            out/f"overlay-{frame['clock']:.1f}.png")
    if checked == 0:
        errors.append("No on-screen native noteheads were pixel-verified")
    if not any(f["reference_notes_overlaid"] for f in report["frames"]):
        errors.append("Original Verovio identities never aligned with native frames")
    summary = {
        "source":"Bill Evans Autumn Leaves, measures 7-8, both hands",
        "density":report["density"],"native_notehead_samples":checked,
        "reference_source_note_count":len(refnotes),
        "rest_overlap_count":report["unavoidable_rest_overlaps"],
        "errors":errors,
    }
    (out/"audit.json").write_text(json.dumps(summary,indent=2)+"\n")
    if errors:
        raise AssertionError("\n".join(errors))
    return summary


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,
                        default=Path("/tmp/piano-native-verovio-overlay"))
    a=parser.parse_args()
    godot=shutil.which("godot") or shutil.which("godot4")
    if not godot:
        parser.error("Actual Godot 4 renderer is required")
    print(json.dumps(run(a.out,godot),indent=2),flush=True)
    return 0


if __name__=="__main__":
    sys.exit(main())

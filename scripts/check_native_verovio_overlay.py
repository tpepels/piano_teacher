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
from dataclasses import dataclass
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
AUTUMN_FILE = "Bill_Evans_on_Autunm_Leaves_From_the_Album_Portrait_in_Jazz.midi"
# Preserve the regression threshold that would have caught the 438px/beat
# user screenshot. More complex pieces use independently specified budgets.
MAX_AUTUMN_DENSITY = 400.0


@dataclass(frozen=True)
class AuditCase:
    name: str
    filename: str
    first_bar: int
    last_bar: int
    hand: str = "both"
    max_density: float = 640.0
    max_tiny_rests: int = 8
    max_dots: int = 2
    features: tuple[str, ...] = ()
    min_lookahead_beats: float = 0.0


# Explicit, pinned real MIDI corpus. Case changes require an intentional
# review: CI must never silently drop a hard score or select easy passages.
CASES = (
    AuditCase("autumn-7-8-both", AUTUMN_FILE, 7, 8,
              max_density=MAX_AUTUMN_DENSITY, max_tiny_rests=2),
    AuditCase("autumn-1-2-right", AUTUMN_FILE, 1, 2, "right"),
    AuditCase("ala-1-2-left", "Ala_–_Joep_Beving.midi", 1, 2, "left"),
    AuditCase("chopin-1-2-right",
              "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", 1, 2, "right"),
    AuditCase("chopin-5-6-both",
              "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", 5, 6,
              min_lookahead_beats=1.75, features=("triplet_turn",)),
    AuditCase("danny-boy-1-2-both", "Danny_Boy(Bill_Evans_Ver_).midi", 1, 2),
    AuditCase("merry-go-round-1-2-both", "Merry-Go-Round-of-Life.midi", 1, 2),
    AuditCase("peace-piece-1-2-both", "Peace_Piece_-_Bill_Evans_(Piano_Solo).midi", 1, 2),
    AuditCase("waltz-1-2-both", "Waltz_for_Debby.midi", 1, 2),
    AuditCase("fidelity-chord-ties",
              "tests/fixtures/musical_fidelity/xml_chord_ties.musicxml",
              1, 2, features=("chords","ties")),
    AuditCase("fidelity-quintuplets",
              "tests/fixtures/musical_fidelity/xml_quintuplets.musicxml",
              1, 1, "right", features=("tuplets",)),
    AuditCase("fidelity-grandstaff",
              "tests/fixtures/musical_fidelity/xml_grandstaff_voices.musicxml",
              1, 1, features=("grandstaff",)),
    AuditCase("fidelity-key-change",
              "tests/fixtures/musical_fidelity/xml_keys_spelling.musicxml",
              1, 2, "right", features=("key_change",)),
    AuditCase("fidelity-sparse-rests",
              "tests/fixtures/musical_fidelity/midi_sparse_rests.mid",
              1, 2, "right", features=("rests",)),
    AuditCase("fidelity-midi-triplets",
              "tests/fixtures/musical_fidelity/midi_triplets.mid",
              1, 1, "right", features=("tuplets",)),
)



def selected_cases(only: str | None = None) -> tuple[AuditCase, ...]:
    matches = tuple(c for c in CASES if not only or only.lower() in c.name.lower()
                    or only.lower() in c.filename.lower())
    if not matches:
        raise ValueError(f"No native overlay cases match {only!r}")
    return matches


def fixture(case: AuditCase = CASES[0]) -> tuple[dict, object]:
    source = ROOT / (case.filename if "/" in case.filename
                     else "midi/" + case.filename)
    piece, _ = import_piece(source)
    assert 1 <= case.first_bar <= case.last_bar < len(piece.bar_boundaries)
    first = piece.bar_boundaries[case.first_bar - 1]
    end = piece.bar_boundaries[case.last_bar]
    notes = tuple(n for n in piece.notes if first <= n.start < end)
    assert notes, f"{case.name}: source passage unexpectedly empty"
    phrase = Phrase(1, case.first_bar, case.last_bar, first, end, notes)
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
                              hand=case.hand)
    engraving = render_layout(score, case.first_bar, case.last_bar, case.hand,
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
        "first_bar": case.first_bar, "last_bar": case.last_bar,
        "sample_beats": [round(i * (end-first) / 4, 8) for i in range(4)],
        "hand": case.hand,
        "xml": score.musicxml,
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


def feature_errors(model: dict, case: AuditCase) -> list[str]:
    """Independently assert that each named challenging fixture tests its goal."""
    if not case.features:
        return []
    events = model["notation_events"]
    notes = [e for e in events if e["kind"] == "note"]
    from collections import Counter
    simultaneous = Counter((e.get("staff"), e.get("beat"), e.get("voice"))
                           for e in notes)
    measures = model.get("measures", [])
    pitched = sorted((e for e in notes if e.get("staff") == "right"),
                     key=lambda e:float(e.get("beat",0)))
    def matched_turn():
        for i in range(len(pitched)-2):
            group = pitched[i:i+3]
            if not all(e.get("note_type") == "32nd" and
                       (e.get("time_modification") or {}).get("actual") == 3 and
                       (e.get("time_modification") or {}).get("normal") == 2
                       for e in group):
                continue
            if all(abs(float(group[j+1]["beat"])-float(group[j]["beat"])
                       -1.0/12.0) < 2e-6 for j in (0,1)):
                return True
        return False
    observed = {
        "chords": any(count > 1 for count in simultaneous.values()),
        "ties": any(not e.get("is_attack", True) for e in notes),
        "tuplets": any(e.get("time_modification") for e in notes),
        "grandstaff": {"left", "right"} <= {e.get("staff") for e in notes},
        "key_change": len({tuple(sorted(m["keys"].items())) for m in measures}) > 1,
        "rests": sum(e["kind"] == "rest" for e in events) >= 2,
        "triplet_turn": matched_turn() if "triplet_turn" in case.features else False,
    }
    return [f"{case.name} stopped exercising required {feature} notation"
            for feature in case.features if not observed.get(feature, False)]


def readability_errors(model: dict, diagnostics: dict,
                       case: AuditCase = CASES[0]) -> list[str]:
    """Fail on known engraving defects, with explicit per-passage budgets."""
    errors = feature_errors(model, case)
    if diagnostics["density"] > case.max_density:
        errors.append(f"{case.name} inflated to {diagnostics['density']:.1f} "
                      f"px/beat (max {case.max_density:.1f})")
    if case.min_lookahead_beats:
        available = float(diagnostics.get("density_witness", {}).get(
            "available_lookahead_beats", 0.0))
        if available + 1e-5 < case.min_lookahead_beats:
            errors.append(f"{case.name}: only {available:.2f} beats ahead "
                          f"(minimum {case.min_lookahead_beats:.2f})")
    if diagnostics["unavoidable_rest_overlaps"]:
        errors.append("Native rests collide with other voice ink")
    events = model["notation_events"]
    tiny_rests = [n for n in events if n["kind"] == "rest" and
                  n["note_type"] in {"32nd","64th","128th"}]
    if len(tiny_rests) > case.max_tiny_rests:
        errors.append("Excessive tiny printed rests in %s (%d; maximum %d)" %
                      (case.name, len(tiny_rests), case.max_tiny_rests))
    gap = float(diagnostics.get("staff_gap", 0.0))
    if gap <= 0.0:
        errors.append("Native staff has no valid layout scale")
    else:
        centers = diagnostics.get("staff_centers", {})
        for frame in diagnostics.get("frames", []):
            for rest in frame.get("rests", []):
                staff = str(rest.get("hand", ""))
                if staff not in centers:
                    errors.append("Rest has no native staff: "+str(rest["id"]))
                    continue
                if abs(float(rest["y"])-float(centers[staff])) > 3.2*gap:
                    errors.append("Rest displaced too far from its staff: "+
                                  str(rest["id"]))
    if any(n["kind"] == "note" and n["dots"] > case.max_dots for n in events):
        errors.append("Unconventional triple/quadruple-dot notation returned "
                      f"in {case.name}")
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


def run(out: Path, godot: str, case: AuditCase = CASES[0]) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    data, engraving = fixture(case)
    model = data["model"]
    # Preserve the actual lesson MusicXML as the single reference score.
    (out/"score.musicxml").write_text(data.pop("xml"),encoding="utf-8")
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
    errors = readability_errors(model, report, case)
    reference = Image.open(out/"verovio-0.png")
    refnotes = engraving.layout["notes"]
    printed_ids = {n["id"] for n in model["notation_events"] if n["kind"] == "note"}
    reference_ids = {n["id"] for n in refnotes}
    if reference_ids != printed_ids:
        errors.append(f"{case.name}: Verovio/native note IDs differ: "
                      f"{len(reference_ids)} reference, {len(printed_ids)} native")
    checked = 0
    rendered_ids = set()
    registered_ids = set()
    active_pixel_samples = 0
    note_staff = {e["id"]:e["staff"] for e in model["notation_events"]
                  if e["kind"] == "note"}
    active_hand = model["active_hand"]

    def is_active(staff: str) -> bool:
        return active_hand == "both" or active_hand == staff

    for frame in report["frames"]:
        screenshot = Image.open(out/frame["file"])
        heads = frame["noteheads"]
        expected = frame.get("expected_noteheads", {})
        for ident, expected_x in expected.items():
            if ident not in heads:
                errors.append(f"{case.name}: Native omitted visible note {ident} "
                              f"at {frame['clock']:.3f}")
            elif abs(heads[ident][0] - expected_x) > 2.4 * report["staff_gap"]:
                errors.append(f"{case.name}: Printed onset drift for {ident} "
                              f"at {frame['clock']:.3f}")
        for ident, (x,y) in heads.items():
            if 20 < x < screenshot.width-20 and 20 < y < screenshot.height-20:
                rendered_ids.add(ident)
                checked += 1
                if is_active(note_staff.get(ident, "")):
                    active_pixel_samples += 1
                if is_active(note_staff.get(ident, "")) and visible_ink(screenshot,x,y) < 5:
                    errors.append(f"Missing rendered native notehead {ident} "
                                  f"at beat {frame['clock']}")
        for rest in frame["rests"]:
            if (is_active(rest["hand"]) and
                    30 < rest["x"] < screenshot.width-30):
                if visible_ink(screenshot,rest["x"],rest["y"],26) < 7:
                    errors.append("Missing native rest pixels: "+str(rest["id"]))
        frame["reference_notes_overlaid"] = draw_overlay(
            reference.copy(),screenshot,refnotes,heads,
            out/f"overlay-{frame['clock']:.2f}.png")
        registered_ids.update(set(heads) & reference_ids)
    if checked == 0:
        errors.append("No on-screen native noteheads were checked")
    if active_pixel_samples == 0:
        errors.append("No active-hand noteheads were pixel-verified")
    if not registered_ids:
        errors.append("Original Verovio identities never aligned with native frames")
    if rendered_ids - reference_ids:
        errors.append(f"Native rendered {len(rendered_ids-reference_ids)} "
                      "notes absent from Verovio")
    summary = {
        "source":f"{case.filename}, measures {case.first_bar}-{case.last_bar}, {case.hand}",
        "case":case.name,
        "density":report["density"],
        "density_witness":report.get("density_witness", {}),
        "native_notehead_samples":checked,
        "reference_source_note_count":len(refnotes),
        "distinct_native_noteheads":len(rendered_ids),
        "active_notehead_pixel_samples":active_pixel_samples,
        "registered_noteheads":len(registered_ids),
        "tiny_rests":sum(1 for n in model["notation_events"] if
                         n["kind"] == "rest" and n["note_type"] in
                         {"32nd","64th","128th"}),
        "maximum_dots":max((n["dots"] for n in model["notation_events"]
                            if n["kind"] == "note"), default=0),
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
    parser.add_argument("--only", help="Case name or MIDI filename substring")
    a=parser.parse_args()
    godot=shutil.which("godot") or shutil.which("godot4")
    if not godot:
        parser.error("Actual Godot 4 renderer is required")
    cases = selected_cases(a.only)
    results = []
    errors = []
    for case in cases:
        directory = a.out / case.name
        try:
            summary = run(directory, godot, case)
            results.append(summary)
            print(f"PASS {case.name}: {summary['native_notehead_samples']} pixels "
                  f"checked; {summary['density']:.1f} px/beat; limiting ink: "
                  + json.dumps(summary["density_witness"],sort_keys=True),
                  flush=True)
        except Exception as exc:
            errors.append({"case":case.name,"error":str(exc)})
            print(f"FAIL {case.name}: {exc}",file=sys.stderr,flush=True)
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"summary.json").write_text(json.dumps({
        "passed":len(results),"failed":len(errors),"results":results,
        "failures":errors},indent=2)+"\n")
    print(f"Native Verovio overlay: {len(results)} passed, "
          f"{len(errors)} failed",flush=True)
    return 1 if errors else 0


if __name__=="__main__":
    sys.exit(main())

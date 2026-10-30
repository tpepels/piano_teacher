"""A two-score current-revision diagnostic sample, not a library audit.

Original real MIDI supplies source attacks. The generated score supplies the
written glyph denominator. Actual Godot PNGs provide every measured pixel.
Unselected events stay unverified and cannot be added to current visual
coverage. This probe reports sample mismatches without silently excluding them.
"""
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels, verify_all_rest_pixels
from piano_teacher.notation.proof import read_written_score
from scripts.check_native_verovio_overlay import AuditCase, fixture

ROOT = Path(__file__).resolve().parents[1]

SAMPLES = {
    "real-score-rests": AuditCase(
        "real-score-rests", "Peace_Piece_-_Bill_Evans_(Piano_Solo).midi", 1, 2, "both"),
    "real-score-dense": AuditCase(
        "real-score-dense", "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", 5, 6, "both"),
}


@pytest.mark.parametrize("name", tuple(SAMPLES))
def test_fresh_real_score_framebuffer_obligations(name, tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    assert godot, "Current-revision Godot renderer is required"
    case = SAMPLES[name]
    prepared, _ = fixture(case)
    assert not prepared["source_errors"], prepared["source_errors"]
    xml = prepared["xml"]
    written = read_written_score(xml)
    construct = "rest" if name == "real-score-rests" else "note"
    candidates = [event for event in written.symbols
                  if event["kind"] == construct and event["visible"]]
    assert candidates, f"No source written {construct}s in {case.filename}"
    counts = Counter(round(float(event["beat"]), 8) for event in candidates)
    # Pinned score, explicit deterministic selection from the complete
    # independent written inventory. Two densest onsets for the Chopin case.
    beats = sorted(counts, key=lambda beat: (-counts[beat], beat))[:2]
    # A real-score passage with one rest onset still has one real
    # source-bound pixel obligation; do not invent a second written rest.
    minimum = 1 if construct == "rest" else 2
    assert len(beats) >= minimum and all(counts[beat] >= 1 for beat in beats), counts
    if construct == "note":
        assert max(counts.values()) >= 2, "Chosen passage does not test dense simultaneous heads"
    prepared.update(sample_beats=beats, phase3_full=True)
    folder = tmp_path / name
    folder.mkdir()
    (folder / "score.musicxml").write_text(xml)
    (folder / "fixture.json").write_text(json.dumps(prepared))
    result = subprocess.run(
        [godot, "--path", str(ROOT / "godot"), "--audio-driver", "Dummy",
         "--rendering-method", "gl_compatibility", "--script",
         str(ROOT / "tests/godot/native_verovio_overlay.gd"),
         "--", str(folder / "fixture.json"), str(folder)],
        capture_output=True, text=True, timeout=70,
        env={**os.environ, "LIBGL_ALWAYS_SOFTWARE": "1"})
    (folder / "godot.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, (result.stdout + result.stderr)[-3500:]
    assert all((folder / f"native-{beat:.5f}.png").is_file() for beat in beats)

    report = (verify_all_rest_pixels(xml, folder, hand="both") if construct == "rest"
              else verify_all_notehead_pixels(
                  xml, folder, hand="both", rail_clocks=tuple(beats)))
    (folder / "independent-pixel-report.json").write_text(json.dumps(report, indent=2))
    measured = [row for row in report["measured"]
                if round(float(row["beat"]), 8) in beats]
    selected_expected = sum(counts[beat] for beat in beats)
    assert len(measured) == selected_expected, {
        "selected": beats, "expected": selected_expected, "found": len(measured)}
    status = Counter(row["status"] for row in measured)
    evidence = {
        "case": name,
        "source": case.filename,
        "selected_beats": beats,
        "written_construct": construct,
        "source_writing_denominator": len(candidates),
        "selected_denominator": selected_expected,
        "selected_verified": status["verified"],
        "selected_unverified": status["unverified"],
        "selected_ambiguous": status["ambiguous"],
        "selected_mismatch": status["mismatch"],
        "unselected_source_symbols": len(candidates) - selected_expected,
        "full_score_visual_complete": False,
        "selected_rows": measured,
    }
    (folder / "sample-evidence.json").write_text(json.dumps(evidence, indent=2))
    # Failure remains a failing physical claim, never an xfail/waiver.
    assert status["verified"] == selected_expected, evidence
    if construct == "rest":
        assert all(row["placement_evidence"]["status"] == "verified"
                   for row in measured), evidence

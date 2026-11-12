"""G1: every chord draws, and where Verovio puts its heads.

The adversarial fixtures in tests/fixtures/g1_chords go through the import
and engraving path of a user's file and the production native view (see
tests/chord_engraving_probe.py). Each chord must be painted with every head
where Verovio's own SVG of the same measure has it: same column, same side
of the stem, same staff position, relative to the chord's leader.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from chord_engraving_probe import FIXTURES, probe

CASES = json.loads((FIXTURES / "cases.json").read_text())
CASE_NAMES = sorted({case["case"] for cases in CASES.values() for case in cases})
# MusicXML-only and unreachable from the product's input: MIDI, the only
# user input, cannot carry grace notes or arpeggio marks. From MusicXML the
# native view refuses the whole exercise: grace chords and arpeggio marks
# have no native painter, so source_annotations lists them as unrendered
# source expressions (docs/midi-transcription-rules.md, Chords).
SCORE_LEVEL_REFUSALS = {"grace-chord", "arpeggiated-chord"}
UNRENDERED = "Source expression requires original Verovio engraving"
# A quarter and an eighth at one onset are two voices, not a chord: no chord
# row. test_humanised_releases_import_as_one_chord checks the import.
NOT_A_CHORD = {"genuinely-different-values"}


def _godot() -> str | None:
    return shutil.which("godot") or shutil.which("godot4")


@pytest.fixture(scope="module")
def rows(tmp_path_factory):
    if not _godot():
        pytest.skip("Godot 4 unavailable")
    _, result = probe(work=tmp_path_factory.mktemp("g1-chord-probe"))
    return result


def test_every_case_reaches_the_native_view(rows):
    found = {row["case"] for row in rows}
    assert "?" not in found, [r for r in rows if r["case"] == "?"]
    assert set(CASE_NAMES) - NOT_A_CHORD == found


@pytest.mark.parametrize("case", CASE_NAMES)
def test_chord_case_draws_where_verovio_puts_its_heads(rows, case):
    mine = [row for row in rows if row["case"] == case]
    if case in NOT_A_CHORD:
        assert not mine, mine
        return
    assert mine
    if case in SCORE_LEVEL_REFUSALS:
        assert all(row["outcome"] == "refused" and row["detail"] == UNRENDERED
                   for row in mine), mine
        return
    for row in mine:
        assert row["outcome"] == "drawn", (
            f"{case}: {' '.join(row['names'])} {row['outcome']}: {row['detail']} [{row['key']}]")
        # Every head is bound to its own event, so status, fingering and
        # interaction find each head by its id.
        assert set(row["native"]) == set(row["members"])


# Hard shapes measured in actual pixels: overprinted unisons, three heads on
# one position, flipped seconds, far ledger heads in the displaced column,
# C clefs, a beamed unison pair. All have filled heads.
FRAMEBUFFER_CASES = {
    "triple-g-flat-natural-sharp", "triple-f-plus-seconds", "alto-clef-triple",
    "chromatic-cluster-down", "unison-pair-down", "asymmetric-low-anchor",
    "asymmetric-high-anchor", "far-ledger-joins-column", "beamed-unisons",
    "bass-clef-rh-chord",
}


def _coverage(ink: np.ndarray, x: float, y: float, gap: float) -> float:
    left, right = round(x - .3 * gap), round(x + .3 * gap)
    top, bottom = round(y - .2 * gap), round(y + .2 * gap)
    patch = ink[max(0, top):bottom + 1, max(0, left):right + 1]
    return float(patch.mean()) if patch.size else 0.0


def test_framebuffer_heads_sit_where_verovio_engraves_them(tmp_path):
    if not _godot() or not os.environ.get("DISPLAY"):
        pytest.skip("Real native framebuffer checks require Godot 4 and DISPLAY")
    from piano_teacher.notation.pixel_ink import bright
    from piano_teacher.notation.pixel_proof import detect_staff_lines

    capture = tmp_path / "frames"
    capture.mkdir()
    _, captured = probe(capture=capture, work=tmp_path,
                        capture_cases=FRAMEBUFFER_CASES | RAIL_CASES,
                        fingering_cases=RAIL_CASES)
    checked = {row["case"] for row in captured if row.get("png")}
    assert FRAMEBUFFER_CASES | RAIL_CASES <= checked, (FRAMEBUFFER_CASES | RAIL_CASES) - checked
    failures = []
    for row in captured:
        if not row.get("png") or row["case"] not in FRAMEBUFFER_CASES | RAIL_CASES:
            continue
        with Image.open(row["png"]) as picture:
            ink = bright(picture)
            staves = detect_staff_lines(picture)
        # The staff space comes from the pixels, not from the renderer.
        gap = staves[row["staff"]].gap
        assert abs(gap - row["gap"]) < .03 * row["gap"], (row["case"], gap, row["gap"])
        lx, ly = row["native"][row["leader"]]
        expected = {ident: (lx + dx * gap, ly + dy * gap)
                    for ident, (dx, dy) in row["verovio"].items()}
        for ident, (x, y) in expected.items():
            name = row["names"][row["members"].index(ident)]
            filled = _coverage(ink, x, y, gap)
            if filled < .6:
                failures.append(f"{row['case']} {name}: no head ink at Verovio's position ({filled:.2f})")
            dx = row["verovio"][ident][0]
            if abs(dx) > .5:
                # A displaced head must not (also) sit in the leader's column,
                # unless a head a second away there reaches into the box.
                column = x - dx * gap
                occupied = any(abs(ox - column) < .6 * gap and abs(oy - y) < .6 * gap
                               for ox, oy in expected.values())
                empty = _coverage(ink, column, y, gap)
                if not occupied and empty > .25:
                    failures.append(f"{row['case']} {name}: ink in the undisplaced column ({empty:.2f})")
        failures += _rail_band_failures(row, ink, gap)
    assert not failures, failures


# The lowest ledger chords, each head fingered: notes and digits must stay
# above the band where the practice stage draws its progress rail.
RAIL_CASES = {"wide-ledger-lh", "ledger-cluster-low"}
RAIL_CLEARANCE = 60  # view_base.gd PROGRESS_RAIL_CLEARANCE


def _rail_band_failures(row, ink, gap) -> list[str]:
    if row["case"] not in RAIL_CASES:
        return []
    failures = []
    band = ink[ink.shape[0] - RAIL_CLEARANCE:, :]
    if band.any():
        failures.append(f"{row['case']}: ink in the progress rail band, rows "
                        f"{ink.shape[0] - RAIL_CLEARANCE + int(band.any(axis=1).argmax())}..")
    low = max(y for _, y in row["native"].values())
    x = row["native"][row["leader"]][0]
    under = ink[round(low + .6 * gap):ink.shape[0] - RAIL_CLEARANCE,
                max(0, round(x - 2 * gap)):round(x + 2 * gap)]
    if not under.any():
        failures.append(f"{row['case']}: no fingering ink under the lowest head")
    return failures


def _bars(first: int):
    """The fixture MIDI's exercise starting at a bar, through the real import."""
    from piano_teacher.music import load_midi
    from piano_teacher.notation.lesson import build_lesson_score
    from piano_teacher.notation.model import build_score_model
    from chord_engraving_probe import model_chords

    piece = load_midi(FIXTURES / "g1_chords.mid")
    phrase = next(p for p in piece.phrases if p.first_bar == first)
    model = build_score_model(build_lesson_score(
        phrase, boundaries=piece.bar_boundaries, time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures), boundaries=piece.bar_boundaries)
    return model, model_chords(model)


def test_humanised_releases_import_as_one_chord():
    # Performed MIDI releases a chord's keys a few ticks apart (1.0, 1.02 and
    # .97 beat). They share one 16th-grid release within the display
    # tolerance, so they are one quarter chord, not three voices.
    model, chords = _bars(19)
    by_beat = {(c["measure"], c["bar_beat"]): c for c in chords}
    assert by_beat[(19, 0.0)]["names"] == ["C4", "E4", "G4"]
    assert by_beat[(19, 0.0)]["kind"] == "quarter"
    assert by_beat[(19, 1.0)]["names"] == ["D4", "F4", "A4", "C5"]
    assert by_beat[(19, 1.0)]["kind"] == "half"
    # A quarter and an eighth at one onset are genuinely different values.
    assert (19, 3.0) not in by_beat
    start = next(m["start_beat"] for m in model["measures"] if m["number"] == 19)
    values = {e["note_type"] for e in model["notation_events"]
              if e["kind"] == "note" and e["measure"] == 19 and e["beat"] - start == 3.0}
    assert values == {"quarter", "eighth"}


def test_held_bass_stays_its_own_voice_under_moving_humanised_chords():
    model, chords = _bars(19)
    left = [c for c in chords if c["measure"] == 20 and c["staff"] == "left"]
    assert [c["names"] for c in left] == [["E3", "G3"], ["F3", "A3"], ["E3", "G3"], ["D3", "F3"]]
    assert all(c["kind"] == "quarter" for c in left)
    bass = [e for e in model["notation_events"] if e["kind"] == "note"
            and e["measure"] == 20 and e["spelling"]["step"] == "C" and e["spelling"]["octave"] == 2]
    assert len(bass) == 1 and bass[0]["note_type"] == "whole"
    assert bass[0]["voice"] not in {c["voice"] for c in left}


def test_every_view_in_the_practice_stage_clears_the_progress_rail():
    import subprocess
    if not _godot():
        pytest.skip("Godot 4 unavailable")
    root = FIXTURES.parents[2]
    proc = subprocess.run(
        [str(root / "scripts/godot-test.sh"), "60", "--headless", "--path", str(root / "godot"),
         "--script", str(root / "tests/godot/practice_stage_rail_clearance.gd")],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0 and "RAIL_CLEARANCE_FAILURES:0" in proc.stdout, proc.stdout[-3000:]

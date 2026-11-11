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
# Not producible from MIDI. From MusicXML the native view refuses the whole
# exercise: grace chords and arpeggio marks have no native painter yet, so
# score_annotations lists them as unrendered source expressions.
SCORE_LEVEL_REFUSALS = {"grace-chord", "arpeggiated-chord"}
UNRENDERED = "Source expression requires original Verovio engraving"


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
    assert set(CASE_NAMES) == found


@pytest.mark.parametrize("case", CASE_NAMES)
def test_chord_case_draws_where_verovio_puts_its_heads(rows, case):
    mine = [row for row in rows if row["case"] == case]
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
    _, captured = probe(capture=capture, work=tmp_path, capture_cases=FRAMEBUFFER_CASES)
    checked = {row["case"] for row in captured if row.get("png")}
    assert FRAMEBUFFER_CASES <= checked, FRAMEBUFFER_CASES - checked
    failures = []
    for row in captured:
        if not row.get("png") or row["case"] not in FRAMEBUFFER_CASES:
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
    assert not failures, failures

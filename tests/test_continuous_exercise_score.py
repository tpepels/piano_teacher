"""Regression checks for freshly engraved one-system practice exercises.

Only exercise-sized material uses the new path. Longer works retain the
existing multi-page renderer until a native vector camera is available.
"""
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.music import Note, Phrase
from piano_teacher.reading_spacing import space_for_continuous_reading
from piano_teacher.score import render_layout


def _exercise(bars=8):
    notes = tuple(
        Note(float(i), i + 1.0, 60 + i % 7, 0, 0, hand)
        for i in range(bars * 3)
        for hand in ("right", "left")
    )
    return Phrase(1, 1, bars, 0, bars * 3, notes)


def test_continuous_source_has_no_encoded_page_or_system_splices():
    xml = build_lesson_score(_exercise()).musicxml
    continuous, options = space_for_continuous_reading(xml, 44)
    root = ET.fromstring(continuous)
    assert options["breaks"] == "none"
    assert options["noJustification"]
    assert options["pageWidth"] > 2200
    assert not any(
        instruction.get("new-system") == "yes" or instruction.get("new-page") == "yes"
        for instruction in root.iter("print")
    )
    assert len(root.findall("./part[@id='RH']/measure")) == 8


@pytest.mark.parametrize("bpm", (44, 80))
def test_complete_eight_measure_exercise_is_newly_engraved_as_one_system(bpm):
    pytest.importorskip("verovio")
    pytest.importorskip("music21")
    phrase = _exercise()
    score = render_layout(
        build_lesson_score(phrase), 1, 8, "right",
        total_beats=24, bpm=bpm, continuous=True,
    )
    assert score.layout["continuous_score"], "Eight-measure exercise was unexpectedly repaginated"
    assert len(score.pages) == score.layout["pages"] == 1
    assert len(score.layout["systems"]) == 1
    assert len(score.layout["systems"][0]["staff_lines"]) == 10
    assert not score.layout["strip_trim_repeated_headers"]
    assert not score.layout["strip_time_proportional"]
    assert len(score.layout["anchors"]) >= 24
    assert all(
        left["x"] <= right["x"]
        for left, right in zip(score.layout["anchors"], score.layout["anchors"][1:])
    )
    assert len(score.layout["attack_map"]) == len(phrase.notes)


def test_older_paginated_rendering_is_still_available():
    pytest.importorskip("verovio")
    pytest.importorskip("music21")
    phrase = _exercise()
    regular = render_layout(build_lesson_score(phrase), 1, 8,
                            total_beats=24, bpm=80, continuous=False)
    assert not regular.layout["continuous_score"]


def test_practice_screen_has_fullscreen_exit_and_direct_source_score():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "godot" / "main.gd"
    source = root.read_text(encoding="utf-8")
    assert 'var practice_exit := _button("Exit", _exit_app' in source
    assert 'var rail_exit := _button("Exit", _exit_app' in source
    assert 'source_layout.get("continuous_score", false)' in source
    assert "native_ink_preview or continuous_engraving" in source

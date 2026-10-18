"""Regression checks for freshly engraved one-system practice exercises.

Only exercise-sized material uses the new path. Longer works retain the
existing multi-page renderer until a native vector camera is available.
"""
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.music import Note, Phrase
from piano_teacher import reading_spacing
from piano_teacher.reading_spacing import NOTE_SPACING, RHYTHM_SPACING, space_for_continuous_reading
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


def test_continuous_spacing_is_independent_of_bpm():
    # Editing a transport BPM must never change Verovio's horizontal
    # note density or alter the visibility of upcoming notes.
    xml = build_lesson_score(_exercise()).musicxml
    variants = [space_for_continuous_reading(xml, bpm)
                for bpm in (30, 44, 80, 120)]
    assert all(xml == variants[0][0] for xml, _ in variants)
    assert all(options == variants[0][1] for _, options in variants)
    for _, options in variants:
        assert options["spacingLinear"] == NOTE_SPACING
        assert options["spacingNonLinear"] == RHYTHM_SPACING
        assert options["noJustification"] is True
        assert options["breaks"] == "none"


def test_note_spacing_constant_can_be_tuned_without_changing_tempo(monkeypatch):
    xml = build_lesson_score(_exercise()).musicxml
    _, original = space_for_continuous_reading(xml, 44)
    monkeypatch.setattr(reading_spacing, "NOTE_SPACING", 0.14)
    _, compact = space_for_continuous_reading(xml, 44)
    _, compact_fast = space_for_continuous_reading(xml, 120)
    assert compact["spacingLinear"] == 0.14
    assert compact["pageWidth"] > original["pageWidth"]
    assert compact_fast == compact


def test_verovio_score_positions_are_unchanged_at_different_tempos():
    pytest.importorskip("verovio")
    pytest.importorskip("music21")
    phrase = _exercise()
    notation = build_lesson_score(phrase)
    earlier = render_layout(notation, 1, 8, "right", total_beats=24, bpm=44, continuous=True)
    later = render_layout(notation, 1, 8, "right", total_beats=24, bpm=120, continuous=True)
    assert earlier.layout["continuous_score"] and later.layout["continuous_score"]
    assert earlier.layout["widths"] == pytest.approx(later.layout["widths"])
    assert earlier.layout["heights"] == pytest.approx(later.layout["heights"])
    before = earlier.layout["anchors"]
    after = later.layout["anchors"]
    assert len(before) == len(after)
    assert [a["beat"] for a in before] == pytest.approx(
        [a["beat"] for a in after], abs=1e-7)
    assert [a["x"] for a in before] == pytest.approx(
        [a["x"] for a in after], abs=1e-5)
    assert earlier.layout["attack_map"] == later.layout["attack_map"]


def test_skip_next_lesson_control_stays_visible_in_practice():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "godot" / "main.gd"
              ).read_text(encoding="utf-8")
    assert 'practice_skip_button = _button("Skip → Next lesson"' in source
    assert 'practice_skip_button.visible = bool(parsed.get("loaded", false))' in source
    assert '"reason": "Learner skipped to the next lesson from the practice screen"' in source
    assert 'practice_skip_button.disabled = not bool(parsed.get("skip_available", false))' in source


def test_short_notes_have_more_even_per_beat_scroll_speed(monkeypatch):
    """Measure actual Verovio note positions: no imaginary timing offsets."""
    pytest.importorskip("verovio")
    pytest.importorskip("music21")
    from piano_teacher.music import Note, Phrase

    # 1/4-beat attacks are affected most by Verovio's minimum symbol width.
    # Alternate fast and slow rhythm to detect the camera accelerations.
    phrase_notes = []
    for measure in range(8):
        start = measure * 4
        for beat, duration in ((0, .25), (.25, .25), (.5, .25),
                               (.75, .25), (1, 1), (2, 1), (3, 1)):
            phrase_notes.append(Note(start + beat, start + beat + duration,
                                     60 + int(beat * 4) % 6, 0, 0, "right"))
    phrase = Phrase(1, 1, 8, 0, 32, tuple(phrase_notes))
    notation = build_lesson_score(phrase)
    def rates(spacing):
        monkeypatch.setattr(reading_spacing, "NOTE_SPACING", spacing)
        engraved = render_layout(notation, 1, 8, "right",
                                 total_beats=32, bpm=80, continuous=True)
        assert engraved.layout["continuous_score"]
        points = engraved.layout["anchors"]
        result = []
        for previous, following in zip(points, points[1:]):
            delta = float(following["beat"]) - float(previous["beat"])
            dx = float(following["x"]) - float(previous["x"])
            if .20 < delta <= 1.01 and dx > 0:
                result.append(dx / delta)
        assert len(result) >= 15
        return max(result) / min(result)
    legacy = rates(.03)
    tuned = rates(.095)
    assert tuned <= legacy + 1e-6, (
        "Increasing rhythmic space must not increase speed jumps: "
        f"{legacy:.3f} -> {tuned:.3f}")

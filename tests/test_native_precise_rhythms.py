"""Exact source rhythms: 128th notes and multiple augmentation dots."""
from fractions import Fraction
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.music import Note, Phrase
from piano_teacher.notation.lesson import (
    DIVISIONS, _dotted_ticks, _type, build_lesson_score,
)
from piano_teacher.notation.model import build_score_model


@pytest.mark.parametrize("note_type,dots,expected_ticks", [
    ("quarter", 3, 18900), ("quarter", 4, 19530),
    ("128th", 0, 315), ("128th", 1, None),
])
def test_rhythms_are_spelled_only_on_exact_integer_ticks(
        note_type, dots, expected_ticks):
    beats = {"quarter": Fraction(1), "128th": Fraction(1, 32)}[note_type]
    assert _dotted_ticks(beats, dots) == expected_ticks
    if expected_ticks is not None:
        assert _type(expected_ticks) == (note_type, dots)


@pytest.mark.parametrize("duration_ticks,kind,dots", [
    (18900, "quarter", 3), (19530, "quarter", 4),
    (315, "128th", 0),
])
def test_native_score_preserves_precisely_graded_multi_dot_and_128th(
        duration_ticks, kind, dots):
    duration = duration_ticks / DIVISIONS
    notes = (
        Note(0.0, duration, 72, 0, 0, "right", "right1"),
        Note(duration, 4.0, 74, 0, 0, "right", "right2"),
    )
    phrase = Phrase(1, 1, 1, 0.0, 4.0, notes)
    score = build_lesson_score(phrase, boundaries=(0.0, 4.0),
                               time_signatures=((0.0, 4, 4),))
    root = ET.fromstring(score.musicxml)
    first = next(
        element for element in root.findall("./part[@id='RH']/measure/note")
        if element.findtext("./pitch/step") == "C")
    assert first.findtext("type") == kind
    assert len(first.findall("dot")) == dots
    assert int(first.findtext("duration")) == duration_ticks
    assert first.get("id") in score.note_bindings

    model = build_score_model(score, boundaries=(0.0, 4.0))
    assert model["unrendered_expressions"] == []
    assert len(model["notes"]) == 2
    events = [event for event in model["notation_events"]
              if event["source_id"] == notes[0].source_id]
    assert len(events) == 1
    assert events[0]["note_type"] == kind
    assert events[0]["dots"] == dots
    assert events[0]["duration_beats"] == pytest.approx(duration)
    assert len([e for e in model["notation_events"] if e["is_attack"]]) == 2


def test_sub_tick_dotted_duration_is_never_rounded():
    # Three dots on 64th = 1181.25 divisions, which is not a canonical
    # note onset on a 10080-tick quarter-note grid.
    assert _dotted_ticks(Fraction(1, 16), 3) is None
    assert _dotted_ticks(Fraction(1, 16), 4) is None

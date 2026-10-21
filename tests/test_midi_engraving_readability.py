"""Regression: performance-MIDI rhythms must remain human-readable.

Synthetic polyphonic filler rests exist only to advance independent cursors.
They must not crowd the native score, affect MIDI grading, or inflate the
horizontal density of unrelated noteheads.
"""
from xml.etree import ElementTree as ET

from piano_teacher.music import Note, Phrase
from piano_teacher.notation.lesson import DIVISIONS, build_lesson_score
from piano_teacher.notation.model import build_score_model


def _phrase(notes):
    return Phrase(1, 1, 1, 0.0, 4.0, tuple(notes))


def test_midi_release_just_before_barline_uses_plain_whole_note():
    # Real Autumn Leaves source, bar 8: MIDI key is released 3.79792
    # beats after attack. Triple-dot 3.75 is an engraving artifact.
    note = Note(0, 3.79792, 72, 0, 0, "right", "release-near-bar")
    score = build_lesson_score(_phrase([note]), boundaries=(0.0, 4.0))
    root = ET.fromstring(score.musicxml)
    elements = root.findall("./part[@id='RH']/measure/note")
    sounds = [n for n in elements if n.find("pitch") is not None]
    assert len(sounds) == 1
    assert sounds[0].findtext("type") == "whole"
    assert sounds[0].findtext("duration") == str(4 * DIVISIONS)
    assert not sounds[0].findall("dot")
    assert not [x for x in elements if x.find("rest") is not None]
    # Graded release remains the original MIDI key-off.
    model = build_score_model(score, boundaries=(0.0, 4.0))
    assert model["notes"][0]["duration_beats"] == 3.69792
    assert len([x for x in model["notation_events"] if x["is_attack"]]) == 1


def test_polyphonic_padding_rest_is_hidden_without_changing_note_clock():
    notes = [
        Note(0.0, 2.0, 60, 0, 0, "right", "lower"),
        Note(1.0, 1.5, 72, 0, 0, "right", "upper"),
    ]
    score = build_lesson_score(_phrase(notes), boundaries=(0.0, 4.0))
    root = ET.fromstring(score.musicxml)
    measure = root.find("./part[@id='RH']/measure")
    assert measure.find("backup") is not None
    hidden = measure.findall("note[@print-object='no']")
    assert hidden
    assert all(n.find("rest") is not None for n in hidden)
    model = build_score_model(score, boundaries=(0.0, 4.0))
    displayed = model["notation_events"]
    assert sorted((n["source_id"], n["beat"]) for n in displayed if n["is_attack"]) == [
        ("lower", 0.0), ("upper", 1.0)
    ]
    # The inactive left staff retains one visible whole-bar rest; the
    # active RH retains only its primary-voice rest.
    assert [(n["staff"], n["voice"]) for n in displayed if n["kind"] == "rest"] == [
        ("right", "1"), ("left", "1")
    ]
    assert len(model["notes"]) == 2
    assert {n["id"] for n in model["notes"]} == {"lower", "upper"}


def test_midi_release_far_from_simple_grid_is_not_quantized():
    note = Note(0, 3.6, 72, 0, 0, "right", "long-release")
    score = build_lesson_score(_phrase([note]), boundaries=(0.0, 4.0))
    root = ET.fromstring(score.musicxml)
    pitched = [x for x in root.findall("./part[@id='RH']/measure/note")
               if x.find("pitch") is not None]
    assert sum(int(n.findtext("duration")) for n in pitched) == round(3.6 * DIVISIONS)
    assert build_score_model(score, boundaries=(0.0, 4.0))["notes"][0]["duration_beats"] == 3.6

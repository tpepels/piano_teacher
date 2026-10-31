"""MIDI-only independent-voice engraving must show held pitch duration.

An overlapping C quarter and upper voice of 16ths must not look like a
single beamed chord: the lower held C needs its own down stem, and upper
sixteenths retain up stems and beams. The exact original MIDI releases
and source IDs must be unchanged.
"""
from xml.etree import ElementTree as ET

from piano_teacher.music import Note, Phrase
from piano_teacher.notation.lesson import DIVISIONS, build_lesson_score
from piano_teacher.notation.model import build_score_model


def _phrase(*, held_upper: bool = False):
    lower = 76 if held_upper else 60
    upper = 60 if held_upper else 76
    notes = (
        Note(0, 1, lower, 0, 0, "right", "held-c"),
        Note(0, .25, upper, 0, 0, "right", "quick-0"),
        Note(.25, .5, upper+2, 0, 0, "right", "quick-1"),
        Note(.5, .75, upper+4, 0, 0, "right", "quick-2"),
        Note(.75, 1, upper+5, 0, 0, "right", "quick-3"),
    )
    return Phrase(1, 1, 1, 0, 2, notes)


def _by_pitch_and_time(measure):
    cursor = 0
    previous = 0
    events = []
    for element in measure:
        if element.tag == "backup":
            cursor -= int(element.findtext("duration"))
            continue
        if element.tag != "note":
            continue
        duration = int(element.findtext("duration", "0"))
        onset = previous if element.find("chord") is not None else cursor
        if element.find("pitch") is not None:
            events.append((onset, int(element.findtext("pitch/step") == "C"), element))
        if element.find("chord") is None:
            previous = cursor
            cursor += duration
    return events


def test_independent_lower_c_quarter_and_beamed_upper_sixteenths():
    phrase = _phrase()
    score = build_lesson_score(phrase, boundaries=(0.0, 2.0),
                               time_signatures=((0.0, 2, 4),))
    root = ET.fromstring(score.musicxml)
    measure = root.find("./part[@id='RH']/measure")
    assert len(measure.findall("backup")) >= 1
    pitched = [n for n in measure.findall("note") if n.find("pitch") is not None]
    held = next(n for n in pitched if n.findtext("pitch/step") == "C")
    quick = [n for n in pitched if n is not held]
    assert held.findtext("type") == "quarter"
    assert held.findtext("duration") == str(DIVISIONS)
    assert held.findtext("stem") == "down"
    assert len(quick) == 4
    assert all(n.findtext("type") == "16th" and
               n.findtext("duration") == str(DIVISIONS//4) and
               n.findtext("stem") == "up" for n in quick)
    assert any(n.findall("beam") for n in quick)
    assert held.find("chord") is None
    model = build_score_model(score, boundaries=(0.0, 2.0))
    original = {n["id"]:n["duration_beats"] for n in model["notes"]}
    assert original["held-c"] == 1.0
    assert all(original[f"quick-{index}"] == .25 for index in range(4))


def test_longer_upper_note_and_lower_sixteenths_reverse_stems():
    score = build_lesson_score(_phrase(held_upper=True),
                               boundaries=(0.0, 2.0),
                               time_signatures=((0.0, 2, 4),))
    root = ET.fromstring(score.musicxml)
    pitched = [n for n in root.findall("./part[@id='RH']/measure/note")
               if n.find("pitch") is not None]
    quarter = next(n for n in pitched if n.findtext("type") == "quarter")
    short = [n for n in pitched if n is not quarter]
    assert quarter.findtext("stem") == "up"
    assert all(n.findtext("stem") == "down" for n in short)


def test_monophonic_midi_stems_remain_renderer_decisions():
    phrase = Phrase(1, 1, 1, 0, 2, (
        Note(0, .25, 60, 0, 0, "right", "one"),
        Note(.25, .5, 62, 0, 0, "right", "two")))
    score = build_lesson_score(phrase, boundaries=(0, 2))
    pitched = ET.fromstring(score.musicxml).findall("./part[@id='RH']/measure/note")
    assert all(n.find("stem") is None for n in pitched if n.find("pitch") is not None)

"""Source-MIDI Chopin ornaments are printed as musical tuplets, not 6:5 singletons."""
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.music import Note, Phrase
from piano_teacher.notation.lesson import _phrase_lanes, build_lesson_score
from piano_teacher.notation.model import build_score_model


def _turn():
    # Actual right-hand MIDI note onsets from Chopin Nocturne Op.9/2 at
    # global quarter beats 26.5, 26.58125, 26.6645833 and 26.75.
    # Original 480-PPQ MIDI misses the intended triplet grid by one tick.
    starts = (0.5, 0.58125, 0.664583333333333, 0.75)
    pitches = (77, 79, 77, 76)
    notes = tuple(Note(
        start, start+(0.075 if i < 3 else 0.23541666666667),
        pitch, 0, 0, "right", f"chopin-turn-{i}")
        for i, (start,pitch) in enumerate(zip(starts,pitches)))
    return Phrase(1,1,1,0.0,4.0,notes)


def test_performance_midi_ornament_has_explicit_triplet_score_and_exact_grading():
    phrase = _turn()
    score = build_lesson_score(phrase, boundaries=(0.0,4.0))
    root = ET.fromstring(score.musicxml)
    notes = [n for n in root.findall("./part[@id='RH']/measure/note")
             if n.find("pitch") is not None]
    assert len(notes) == 4
    for n in notes[:3]:
        assert n.findtext("type") == "32nd"
        assert n.findtext("duration") == "840"
        assert n.findtext("time-modification/actual-notes") == "3"
        assert n.findtext("time-modification/normal-notes") == "2"
    assert len(root.findall(".//tuplet[@type='start']")) >= 1
    assert len(root.findall(".//tuplet[@type='stop']")) >= 1
    model = build_score_model(score, boundaries=(0.0,4.0))
    right = sorted((n for n in model["notation_events"] if
                    n["kind"] == "note" and n["staff"] == "right"),
                   key=lambda e:e["beat"])
    assert [n["beat"] for n in right] == pytest.approx(
        [0.5,7/12,2/3,0.75],abs=1e-7)
    assert len([n for n in right if n["is_attack"]]) == 4
    # No fabricated MIDI attacks and no loss of the performed onset.
    source_times = [note.start for note in phrase.notes]
    assert sorted(n["source_beat"] for n in score.note_bindings.values()
                  if n["is_attack"]) == pytest.approx(sorted(source_times))


def test_unstructured_two_note_rubato_is_not_turned_into_triplets():
    first,second = _turn().notes[:2]
    phrase = Phrase(1,1,1,0.0,4.0,(first,second))
    lanes = _phrase_lanes(phrase,"right")
    onsets = sorted(start for lane in lanes for start,_,_ in lane)
    assert onsets == [round(n.start*10080) for n in phrase.notes]


def test_explicit_source_musicxml_notation_is_never_heuristically_rewritten():
    phrase = _turn()
    lanes = _phrase_lanes(phrase,"right",from_source_musicxml=True)
    onsets = sorted(start for lane in lanes for start,_,_ in lane)
    assert onsets == [round(n.start*10080) for n in phrase.notes]



def test_repeated_midi_swing_becomes_readable_eighths_without_moving_source():
    from piano_teacher.notation.lesson import _midi_swing_onsets
    starts = (0.0, 0.6, 1.0, 1.6, 2.0, 2.6, 3.0)
    notes = tuple(Note(
        start, start+(.35 if start % 1 > .5 else .48),
        65+i, 0, 0, "right", f"swing-{i}")
        for i,start in enumerate(starts))
    phrase = Phrase(1,1,1,0.0,4.0,notes)
    swing = _midi_swing_onsets(phrase,"right")
    assert sorted(swing.values()) == [5040,15120,25200]
    score = build_lesson_score(phrase, boundaries=(0.0,4.0))
    recorded = {round(binding["source_beat"],5):binding["display_beat"]
                for binding in score.note_bindings.values() if binding["is_attack"]}
    assert recorded[.6] == pytest.approx(.5)
    assert recorded[1.6] == pytest.approx(1.5)
    assert recorded[2.6] == pytest.approx(2.5)
    assert recorded[1.0] == pytest.approx(1.0)
    model = build_score_model(score, boundaries=(0.0,4.0))
    assert len(model["notes"]) == len(notes)
    assert sorted(n["onset_beats"] for n in model["notes"]) == list(starts)
    assert all(n["dots"] <= 2 for n in model["notation_events"]
               if n["kind"] == "note")


def test_isolated_offbeat_rubato_is_never_assumed_to_be_swing():
    from piano_teacher.notation.lesson import _midi_swing_onsets
    notes = (
        Note(0.0,.45,60,0,0,"right","first"),
        Note(.6,.94,62,0,0,"right","second"),
        Note(1.0,1.5,64,0,0,"right","third"),
    )
    phrase = Phrase(1,1,1,0.0,4.0,notes)
    assert not _midi_swing_onsets(phrase,"right")
    score = build_lesson_score(phrase, boundaries=(0.0,4.0))
    assert any(abs(b["display_beat"]-.6)<1e-8
               for b in score.note_bindings.values() if b["is_attack"])

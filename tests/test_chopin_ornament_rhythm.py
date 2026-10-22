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



def test_display_notation_is_never_allowed_to_change_the_grading_clock():
    from dataclasses import replace
    phrase = _turn()
    score = build_lesson_score(phrase,boundaries=(0.0,4.0))
    assert build_score_model(score,boundaries=(0.0,4.0))
    bindings = {key:value.copy() for key,value in score.note_bindings.items()}
    modified = next(v for v in bindings.values() if
                    v["notation_timing"] == "triplet" and
                    abs(v["display_beat"]-v["source_beat"]) > 1e-5)
    modified["notation_timing"] = "exact"
    with pytest.raises(ValueError, match="scoring onset"):
        build_score_model(replace(score,note_bindings=bindings),
                          boundaries=(0.0,4.0))
    restored = {key:value.copy() for key,value in score.note_bindings.items()}
    changed = next(v for v in restored.values() if v["notation_timing"] == "triplet")
    changed["source_beat"] += .05
    with pytest.raises(ValueError, match="grading onset"):
        build_score_model(replace(score,note_bindings=restored),
                          boundaries=(0.0,4.0))



def test_swing_keeps_true_playhead_alignment_and_hides_inferred_micro_rest():
    # A swung attack at .6 would miss the start-tempo 100ms grading window
    # if displayed at .5 (150ms at 40 BPM). Never rewrite its onset.
    notes = (
        Note(0.0,.5,72,0,0,"right","first"),
        Note(.6,.95,74,0,0,"right","swing"),
        Note(1.0,1.49,76,0,0,"right","third"),
    )
    phrase = Phrase(1,1,1,0.0,4.0,notes)
    score = build_lesson_score(phrase,boundaries=(0.0,4.0))
    model = build_score_model(score,boundaries=(0.0,4.0))
    tagged = [b for b in score.note_bindings.values()
              if b["source_id"] == "swing" and b["is_attack"]]
    assert len(tagged) == 1
    assert tagged[0]["display_beat"] == pytest.approx(.6,abs=1e-8)
    assert tagged[0]["source_beat"] == pytest.approx(.6,abs=1e-8)
    assert model["notes"][1]["onset_beats"] == pytest.approx(.6)
    root = ET.fromstring(score.musicxml)
    # No rest glyph from the .1 beat inferred performance release gap.
    right_rests = root.findall("./part[@id='RH']/measure/note[@print-object='no']/rest")
    assert right_rests
    assert all(e["beat"] != pytest.approx(.5)
               for e in model["notation_events"] if e["kind"]=="rest"
               and e["staff"]=="right")


def test_explicit_musicxml_still_shows_small_written_rests():
    from piano_teacher.notation.lesson import _render_measure
    measure = ET.Element("measure")
    _render_measure(measure, [[
        (0,5040,[{"source_id":"a","source_beat":0.0,"pitch":72,
                 "hand":"right","spelling":None,"notation_timing":"exact"}]),
        (6048,10080,[{"source_id":"b","source_beat":.6,"pitch":74,
                      "hand":"right","spelling":None,"notation_timing":"exact"}]),
    ]],40320,0,{}, {}, hide_performance_micro_rests=False)
    # The gap is explicitly printed in original MusicXML mode.
    assert [e for e in measure.findall("note")
            if e.find("rest") is not None and
            e.get("print-object") != "no"]

"""The lesson MusicXML contains the same actual required note events."""
from xml.etree import ElementTree as ET
import pytest
from piano_teacher.music import Note, Phrase
from piano_teacher.lesson_score import build_lesson_score, DIVISIONS
from piano_teacher.exercise_generator import generate_variants


def note(pitch, start, end, hand="right"):
    return Note(start,end,pitch,0,0,hand)


def phrase(notes, length=8):
    return Phrase(1,1,2,0,length,tuple(notes))


def pitched(xml):
    root=ET.fromstring(xml)
    result=[]
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            for n in measure.findall("note"):
                p=n.find("pitch")
                if p is not None:
                    result.append((part.get("id"),p.findtext("step"),
                                   p.findtext("octave"),p.findtext("alter","0")))
    return result


def test_skeleton_notation_cannot_include_eliminated_chord_tones():
    source=phrase([note(60,0,1),note(64,0,1),note(67,0,1),note(72,.25,.5),
                   note(48,0,1,"left"),note(52,0,1,"left"),note(55,0,1,"left")])
    stages=generate_variants(source)
    small=pitched(build_lesson_score(stages[0].phrase).musicxml)
    original=pitched(build_lesson_score(stages[-1].phrase).musicxml)
    assert len(small)==2 and len(original)==7
    assert set(small).issubset(set(original))


def test_chords_and_independent_voices_have_correct_backups():
    xml=build_lesson_score(phrase([note(60,0,1),note(64,0,1),
                                   note(67,0,1),note(72,.5,1.5)])).musicxml
    measure=ET.fromstring(xml).find("./part[@id='RH']/measure")
    assert len(measure.findall(".//chord"))==2
    assert [int(x.findtext("duration")) for x in measure.findall("backup")]==[4*DIVISIONS]


def test_unisons_preserve_distinct_required_events():
    xml=build_lesson_score(phrase([note(60,0,1),note(60,0,1)])).musicxml
    measure=ET.fromstring(xml).find("./part[@id='RH']/measure")
    assert len([x for x in measure.findall("note") if x.find("pitch") is not None])==2
    assert len(measure.findall("backup"))==1


def test_cross_measure_note_is_tied_not_reattacked():
    xml=build_lesson_score(phrase([note(65,3,5)])).musicxml
    measures=ET.fromstring(xml).find("./part[@id='RH']").findall("measure")
    # The sounding note starts in bar 1 and continues into bar 2.
    # The second segment must *stop* the tie, not reattack a new note.
    first = [x for x in measures[0].findall("note") if x.find("pitch") is not None]
    second = [x for x in measures[1].findall("note") if x.find("pitch") is not None]
    assert len(first) == len(second) == 1
    assert first[0].find("tie[@type='start']") is not None
    assert first[0].find("tie[@type='stop']") is None
    assert second[0].find("tie[@type='stop']") is not None
    assert second[0].find("tie[@type='start']") is None


def test_three_four_has_correct_beat_length_and_inactive_rest():
    xml=build_lesson_score(phrase([note(74,0,1)],length=6)).musicxml
    root=ET.fromstring(xml)
    time=root.find("part/measure/attributes/time")
    assert time.findtext("beats")=="3" and time.findtext("beat-type")=="4"
    lh=root.find("./part[@id='LH']")
    assert lh.find("measure/attributes/clef/sign").text=="F"
    assert all(x.find("rest") is not None for x in lh.findall(".//note"))


def test_malformed_pitch_raises_instead_of_silent_corruption():
    with pytest.raises(ValueError,match="Invalid MIDI pitch"):
        build_lesson_score(phrase([note(300,0,1)]))


def test_early_midi_release_uses_conventional_printed_duration():
    # Typical piano tutorial MIDI: each key is released 0.1 quarter early.
    # Notation must be a normal quarter, not an exotic 0.9-beat duration
    # followed by an unengraveable 0.1-beat rest.
    source=phrase([note(67,float(i),float(i)+.9) for i in range(8)])
    xml=build_lesson_score(source).musicxml
    measures=ET.fromstring(xml).find("./part[@id='RH']").findall("measure")
    assert len(measures)==2
    for measure in measures:
        sounding=[n for n in measure.findall("note") if n.find("pitch") is not None]
        assert len(sounding)==4
        assert all(int(n.findtext("duration"))==DIVISIONS for n in sounding)
        assert not any(n.find("rest") is not None for n in measure.findall("note"))
    # Lesson source remains precise; the evaluator uses these unchanged notes.
    assert source.notes[0].end == .9


def test_nontrivial_release_remains_precise_when_not_near_a_grid():
    source=phrase([note(60,0,.64)])
    xml=build_lesson_score(source).musicxml
    item=ET.fromstring(xml).find("./part[@id='RH']/measure/note")
    assert int(item.findtext("duration"))==round(.64*DIVISIONS)

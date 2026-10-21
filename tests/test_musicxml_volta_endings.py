"""Source volta-ending import, semantic retention and native time-axis contract."""
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation.musicxml import parse_barline


def _piece(tmp_path):
    xml = """<score-partwise version="4.0"><part-list>
        <score-part id="RH"><part-name>Right hand</part-name></score-part>
        <score-part id="LH"><part-name>Left hand</part-name></score-part>
    </part-list>
    <part id="RH">
      <measure number="1"><attributes><divisions>10080</divisions>
       <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
       <barline location="left"><ending number="1" type="start"/></barline>
       <note><pitch><step>C</step><octave>5</octave></pitch>
         <duration>40320</duration><type>whole</type></note>
      </measure>
      <measure number="2"><note><pitch><step>D</step><octave>5</octave></pitch>
         <duration>40320</duration><type>whole</type></note>
       <barline location="right"><ending number="1" type="stop"/>
         <repeat direction="backward"/></barline>
      </measure>
    </part>
    <part id="LH">
      <measure number="1"><attributes><divisions>10080</divisions>
       <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
       <note><pitch><step>C</step><octave>3</octave></pitch>
         <duration>40320</duration><type>whole</type></note>
      </measure>
      <measure number="2"><note><pitch><step>G</step><octave>3</octave></pitch>
         <duration>40320</duration><type>whole</type></note>
      </measure>
    </part></score-partwise>"""
    filename = tmp_path / "volta.musicxml"
    filename.write_text(xml)
    return load_musicxml(filename, bpm=90)


def test_volta_keeps_correct_source_measures_and_never_repeats_graded_notes(tmp_path):
    piece = _piece(tmp_path)
    assert len(piece.notes) == 4
    assert len(piece.barlines) == 2
    phrase = Phrase(1, 1, 2, 0, 8, piece.notes)
    score = build_lesson_score(phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures, key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes, barlines=piece.barlines,
        source_musicxml=piece.source_musicxml)
    xml = ET.fromstring(score.musicxml)
    assert len(xml.findall(".//ending")) == 4
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    measures = model["measures"]
    assert measures[0]["left_barline"]["ending"] == {
        "number": "1", "type": "start"}
    assert measures[1]["right_barline"]["ending"] == {
        "number": "1", "type": "stop"}
    assert measures[1]["right_barline"]["repeat"] == "backward"
    assert model["duration_beats"] == 8
    assert len(model["notes"]) == 4
    assert len([event for event in model["notation_events"]
                if event["kind"] == "note" and event["is_attack"]]) == 4


@pytest.mark.parametrize("number,kind", [
    ("", "start"), ("foo", "start"), ("1", "typo"), ("1"*20, "stop")])
def test_malformed_volta_endings_are_rejected(number, kind):
    barline = ET.fromstring(
        '<barline location="left"><ending number="%s" type="%s"/></barline>' %
        (number, kind))
    with pytest.raises(ValueError, match="volta"):
        parse_barline(barline)


def test_nonfinal_volta_is_not_silently_discarded_when_excerpt_ends(tmp_path):
    piece = _piece(tmp_path)
    notes = tuple(n for n in piece.notes if n.start < 4)
    score = build_lesson_score(
        Phrase(1, 1, 1, 0, 4, notes),
        boundaries=piece.bar_boundaries, time_signatures=piece.time_signatures,
        barlines=piece.barlines, source_musicxml=piece.source_musicxml)
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    assert model["measures"][0]["left_barline"]["ending"]["type"] == "start"
    assert model["duration_beats"] == 4

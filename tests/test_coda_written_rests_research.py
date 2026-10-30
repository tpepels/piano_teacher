"""Research Coda: original MusicXML rests are first-class, never inferred."""
from pathlib import Path

import pytest

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Note, Phrase
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_written_rests import extract_written_rests


def test_backup_forward_chords_and_hidden_rests_preserve_source_semantics():
    source = """<score-partwise><part id="P1"><measure number="1">
      <attributes><divisions>4</divisions></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration>
        <voice>1</voice></note>
      <backup><duration>16</duration></backup>
      <note><rest/><duration>4</duration><voice>2</voice><staff>2</staff>
        <type>quarter</type></note>
      <forward><duration>4</duration></forward>
      <note print-object="no"><rest/><duration>8</duration>
        <voice>2</voice><staff>2</staff><type>half</type></note>
    </measure></part></score-partwise>"""
    phrase = Phrase(1, 1, 1, 0, 4, (
        Note(0, 4, 60, 0, 0, "right", "xml-p0-m0-e1", "xml-p0-s1-v1"),))
    matrix = MatrixScore.from_phrase(
        phrase, boundaries=(0, 4), source_musicxml=source)
    assert matrix.note_count == 1
    assert matrix.attack_count == 1
    assert matrix.written_rest_count == 2
    assert [(r.source_id, r.voice_id, r.onset, r.end, r.visible)
            for r in matrix.written_rests] == [
        ("xml-p0-m0-e3", "xml-p0-s2-v2", 0, 1, True),
        ("xml-p0-m0-e5", "xml-p0-s2-v2", 2, 4, False)]
    assert [r.note_type for r in matrix.written_rests] == ["quarter", "half"]
    matrix.verify_lossless()


def test_selected_later_measure_inherits_divisions_and_keeps_dotted_full_rest():
    source = """<score-partwise xmlns="http://www.musicxml.org/ns/musicxml">
     <part id="P"><measure number="1"><attributes>
       <divisions>2</divisions></attributes>
       <note><rest/><duration>8</duration><voice>1</voice></note>
     </measure><measure number="2"><attributes>
       <divisions>8</divisions></attributes>
       <note><rest measure="yes"/><duration>24</duration><voice>3</voice>
         <type>whole</type><dot/></note>
     </measure></part></score-partwise>"""
    rests = extract_written_rests(source, first_bar=2, last_bar=2,
                                  boundaries=(4.0, 7.0))
    assert len(rests) == 1
    rest, = rests
    assert (rest.source_id, rest.measure, rest.onset, rest.end) == (
        "xml-p0-m1-e1", 2, 4, 7)
    assert (rest.voice_id, rest.note_type, rest.dots, rest.full_measure) == (
        "xml-p0-s1-v3", "whole", 1, True)


def test_authored_rests_are_not_derived_from_forward_silence():
    source = """<score-partwise><part id="P"><measure number="1">
        <forward><duration>4</duration></forward>
        </measure></part></score-partwise>"""
    assert extract_written_rests(
        source, first_bar=1, last_bar=1, boundaries=(0.0, 4.0)) == ()


def test_source_rest_beyond_bar_fails_closed():
    source = """<score-partwise><part id="P"><measure number="1">
        <note><rest/><duration>5</duration></note>
        </measure></part></score-partwise>"""
    with pytest.raises(ValueError, match="exceeds source measure"):
        extract_written_rests(source, first_bar=1, last_bar=1,
                              boundaries=(0.0, 4.0))


def test_real_written_rest_source_ids_are_preserved():
    fixture = (Path(__file__).parent / "fixtures" / "musical_fidelity" /
               "xml_parallel_tied_voices.musicxml")
    piece = load_musicxml(fixture, bpm=80)
    phrase = Phrase(1, 1, len(piece.bar_boundaries) - 1,
                    piece.bar_boundaries[0], piece.bar_boundaries[-1], piece.notes)
    matrix = MatrixScore.from_phrase(
        phrase, boundaries=piece.bar_boundaries,
        source_musicxml=piece.source_musicxml)
    rest_ids = {rest.source_id for rest in matrix.written_rests}
    assert {"xml-p0-m0-e3", "xml-p0-m1-e4"} <= rest_ids
    assert all(rest.onset < rest.end for rest in matrix.written_rests)
    assert all(rest.voice_id.startswith("xml-p") for rest in matrix.written_rests)
    matrix.verify_lossless()

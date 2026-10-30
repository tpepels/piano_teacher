"""Focused source notation inventory for the Coda research adapter."""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_source_metadata import source_elements


def test_all_written_subtrees_survive_with_source_order_voice_and_beats():
    source = """<score-partwise xmlns="http://www.musicxml.org/ns/musicxml">
      <part id="P"><measure number="1">
        <attributes><divisions>4</divisions><time><beats>4</beats>
        <beat-type>4</beat-type></time><key><fifths>-1</fifths></key>
        <clef><sign>G</sign><line>2</line></clef></attributes>
        <direction><direction-type><dynamics><mf/></dynamics></direction-type>
        <voice>1</voice><staff>1</staff></direction>
        <note><pitch><step>C</step><octave>4</octave></pitch>
        <duration>4</duration><type>quarter</type><voice>1</voice>
        <notations><articulations><staccato/></articulations><slur type="start" number="1"/>
        </notations></note>
        <note><pitch><step>E</step><octave>4</octave></pitch>
        <duration>4</duration><type>quarter</type><voice>1</voice>
        <notations><slur type="stop" number="1"/></notations></note>
        <backup><duration>8</duration></backup>
        <note><rest/><duration>16</duration><voice>2</voice>
        <type>whole</type></note>
        <barline location="right"><bar-style>light-heavy</bar-style></barline>
      </measure></part></score-partwise>"""
    items = source_elements(source, first_bar=1, last_bar=1, boundaries=(0,4))
    assert [x.kind for x in items] == [
        "attributes", "direction", "note", "note", "backup", "note", "barline"]
    assert [x.ordinal for x in items] == list(range(7))
    assert [(x.onset, x.end) for x in items if x.is_timed_note] == [
        (0,1), (1,2), (0,4)]
    assert [x.voice_id for x in items if x.kind == "note"] == [
        "xml-p0-s1-v1", "xml-p0-s1-v1", "xml-p0-s1-v2"]
    assert items[0].source_id == "xml-p0-m0-e0"
    assert items[5].is_rest
    assert ET.fromstring(items[0].xml).find(".//{*}fifths").text == "-1"
    assert ET.fromstring(items[2].xml).find(".//{*}staccato") is not None
    assert ET.fromstring(items[1].xml).find(".//{*}mf") is not None
    assert ET.fromstring(items[6].xml).find(".//{*}bar-style").text == "light-heavy"


def test_selected_measure_keeps_divisions_and_source_indices():
    source = """<score-partwise><part id="P"><measure number="1">
      <attributes><divisions>2</divisions></attributes>
      <note><rest/><duration>8</duration></note></measure>
      <measure number="2"><note><rest/><duration>2</duration></note>
      <note><rest/><duration>6</duration></note></measure></part></score-partwise>"""
    items = source_elements(source, first_bar=2, last_bar=2, boundaries=(4,8))
    assert [x.source_id for x in items] == ["xml-p0-m1-e0", "xml-p0-m1-e1"]
    assert [(x.onset, x.end) for x in items] == [(4,5), (5,8)]


def test_source_metadata_fails_closed_on_out_of_measure_note():
    source = """<score-partwise><part id="P"><measure number="1">
      <note><rest/><duration>5</duration></note></measure></part></score-partwise>"""
    with pytest.raises(ValueError, match="outside selected measure"):
        source_elements(source, first_bar=1, last_bar=1, boundaries=(0,4))


@pytest.mark.parametrize("file", [
    "xml_parallel_tied_voices.musicxml", "xml_trailing_rests.musicxml"
])
def test_real_source_inventory_keeps_complete_measure_children(file):
    path = Path(__file__).parent / "fixtures" / "musical_fidelity" / file
    piece = load_musicxml(path, bpm=80)
    phrase = Phrase(1, 1, len(piece.bar_boundaries)-1,
                    piece.bar_boundaries[0], piece.bar_boundaries[-1], piece.notes)
    matrix = MatrixScore.from_phrase(
        phrase, boundaries=piece.bar_boundaries,
        source_musicxml=piece.source_musicxml)
    root = ET.fromstring(piece.source_musicxml)
    expected = sum(len(measure) for part in root.findall("{*}part")
                   for measure in part.findall("{*}measure"))
    assert len(matrix.notation_elements) == expected
    assert len({x.source_id for x in matrix.notation_elements}) == expected
    assert {x.source_id for x in matrix.notation_elements if x.is_rest} == {
        r.source_id for r in matrix.written_rests}
    for voice in matrix.rest_only_voices:
        assert [x.source_id for x in matrix.source_voice_elements(voice.name)
                if x.is_rest] == [r.source_id for r in voice.written_rests]
    matrix.verify_lossless()

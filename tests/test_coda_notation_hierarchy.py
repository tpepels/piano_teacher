"""Real and synthetic notation-source context invariants for the Coda adapter."""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_notation_hierarchy import (
    measure_contexts, notation_parts)
from piano_teacher.research.coda_source_metadata import source_elements


SOURCE = """<score-partwise version="4.0">
  <work><work-title>Source original title</work-title></work>
  <part-list><score-part id="R"><part-name>Right</part-name></score-part>
             <score-part id="L"><part-name>Left</part-name></score-part></part-list>
  <part id="R">
    <measure number="1">
      <attributes><divisions>2</divisions>
        <key><fifths>-2</fifths></key>
        <time><beats>3</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef></attributes>
      <note><pitch><step>C</step><octave>5</octave></pitch>
        <duration>2</duration><voice>1</voice><type>quarter</type></note>
      <forward><duration>4</duration></forward>
    </measure>
    <measure number="2">
      <note><pitch><step>D</step><octave>5</octave></pitch>
        <duration>2</duration><voice>1</voice><type>quarter</type></note>
      <attributes><key><fifths>1</fifths></key></attributes>
      <direction><direction-type><words>with character</words></direction-type>
        <voice>1</voice></direction>
      <backup><duration>2</duration></backup>
      <note><rest/><duration>6</duration><voice>2</voice>
        <type>half</type><dot/></note>
      <barline location="right"><bar-style>light-heavy</bar-style></barline>
    </measure>
  </part>
  <part id="L">
    <measure number="1">
      <attributes><divisions>2</divisions>
        <clef><sign>F</sign><line>4</line></clef></attributes>
      <note><rest/><duration>6</duration><voice>1</voice><type>half</type><dot/></note>
    </measure>
    <measure number="2">
      <note><rest/><duration>6</duration><voice>1</voice><type>half</type><dot/></note>
    </measure>
  </part>
</score-partwise>"""


def test_source_context_inherits_prior_measure_without_creating_fake_xml():
    elems=source_elements(SOURCE,first_bar=2,last_bar=2,boundaries=(3,6))
    contexts=measure_contexts(SOURCE,first_bar=2,last_bar=2,
                              notation_elements=elems)
    assert len(contexts)==2
    right=contexts[0]
    assert (right.part_index,right.measure)==(0,2)
    assert ET.fromstring(right.at_entry("key").xml).findtext("fifths") == "-2"
    assert ET.fromstring(right.at_entry("clef").xml).findtext("sign") == "G"
    assert ET.fromstring(right.at_entry("time").xml).findtext("beats") == "3"
    assert right.at_entry("divisions").xml.startswith("<divisions>2")
    assert right.at_entry("key").source_measure==1
    assert len(right.changes)==1
    assert right.changes[0].value.kind=="key"
    assert right.changes[0].value.source_id=="xml-p0-m1-e1"
    assert right.changes[0].onset==4
    assert ET.fromstring(right.resulting[1].xml) is not None
    assert next(v for v in right.resulting if v.kind=="key").source_measure==2
    left=contexts[1]
    assert ET.fromstring(left.at_entry("clef").xml).findtext("sign")=="F"
    assert left.changes==()
    assert left.at_entry("key") is None  # No invented key.


def test_source_part_measure_voice_partition_and_unvoiced_notation():
    elements=source_elements(SOURCE,first_bar=2,last_bar=2,boundaries=(3,6))
    contexts=measure_contexts(SOURCE,first_bar=2,last_bar=2,
                              notation_elements=elements)
    parts=notation_parts(elements,contexts)
    assert len(parts)==2
    right=parts[0]
    assert [v.name for v in right.voices]==[
        "xml-p0-s1-v1","xml-p0-s1-v2"]
    assert [e.kind for e in right.unvoiced]==[
        "attributes","backup","barline"]
    assert [e.kind for e in right.measures[0].elements]==[
        "note","attributes","direction","backup","note","barline"]
    ids=[e.source_id for part in parts for measure in part.measures
         for e in measure.elements]
    assert len(ids)==len(elements)==len(set(ids))
    assert {e.source_id for e in elements}==set(ids)
    rest=right.voices[1].elements[0]
    assert ET.fromstring(rest.xml).find("{*}dot") is not None
    assert parts[1].voices[0].name=="xml-p1-s1-v1"


def test_source_context_requires_all_selected_attributes_in_inventory():
    elements=source_elements(SOURCE,first_bar=2,last_bar=2,boundaries=(3,6))
    missing=tuple(e for e in elements if e.source_id!="xml-p0-m1-e1")
    with pytest.raises(ValueError,match="Selected attribute missing"):
        measure_contexts(SOURCE,first_bar=2,last_bar=2,notation_elements=missing)


def test_matrix_preserves_global_xml_and_original_source_context():
    src=Path(__file__).parent/"fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml"
    piece=load_musicxml(src,bpm=80)
    phrase=Phrase(1,1,len(piece.bar_boundaries)-1,
        piece.bar_boundaries[0],piece.bar_boundaries[-1],piece.notes)
    matrix=MatrixScore.from_phrase(phrase,boundaries=piece.bar_boundaries,
                                   source_musicxml=piece.source_musicxml)
    assert matrix.original_musicxml==piece.source_musicxml
    root=ET.fromstring(matrix.original_musicxml)
    assert root.tag.endswith("score-partwise")
    assert len(matrix.notation_parts)==len(root.findall("{*}part"))
    assert all(len(p.measures)==len(piece.bar_boundaries)-1
               for p in matrix.notation_parts)
    assert any(p.voices for p in matrix.notation_parts)
    assert sum(len(m.elements) for p in matrix.notation_parts for m in p.measures
               )==len(matrix.notation_elements)
    matrix.verify_lossless()


@pytest.mark.parametrize("file", [
    "xml_long_multipage.musicxml","xml_trailing_rests.musicxml",
    "xml_parallel_tied_voices.musicxml",
])
def test_real_multi_measure_source_notation_is_not_dropped(file):
    path=Path(__file__).parent/"fixtures/musical_fidelity"/file
    piece=load_musicxml(path,bpm=80)
    phrase=Phrase(1,1,len(piece.bar_boundaries)-1,
        piece.bar_boundaries[0],piece.bar_boundaries[-1],piece.notes)
    matrix=MatrixScore.from_phrase(phrase,boundaries=piece.bar_boundaries,
                                   source_musicxml=piece.source_musicxml)
    original=ET.fromstring(piece.source_musicxml)
    expected=sum(len(m) for part in original.findall("{*}part")
                 for m in part.findall("{*}measure"))
    assert sum(len(m.elements) for part in matrix.notation_parts
               for m in part.measures)==expected
    for part in matrix.notation_parts:
        assert len(part.measures)==len(piece.bar_boundaries)-1
    matrix.verify_lossless()

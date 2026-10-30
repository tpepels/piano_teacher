"""Coda source links: explicit MusicXML arcs, protected inner notes and safe cuts."""
from pathlib import Path

import pytest

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Note, Phrase
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_polyphony import PolyphonicChordifier
from piano_teacher.research.coda_research_strategies import (
    ResearchPartSplitter, ResearchPolyphonicDottedRhythm)
from piano_teacher.research.coda_source_connectors import (
    link_source_connectors, protected_connector_source_ids)
from piano_teacher.research.coda_source_metadata import source_elements


def notation_xml(marks="", second_marks="", *, voice="1", extras=""):
    return f"""<score-partwise><part id="P">
        <measure number="1"><attributes><divisions>1</divisions></attributes>
        <note id="one"><pitch><step>C</step><octave>4</octave></pitch>
          <duration>4</duration><voice>{voice}</voice>
          {marks}</note>{extras}</measure>
        <measure number="2"><note id="two">
          <pitch><step>C</step><octave>4</octave></pitch>
          <duration>4</duration><voice>{voice}</voice>
          {second_marks}</note></measure>
        </part></score-partwise>"""


def _link(xml, *, first=1, last=2, grid=(0, 4, 8)):
    return link_source_connectors(source_elements(
        xml, first_bar=first,last_bar=last,boundaries=grid))


def test_slur_and_double_written_tie_keep_two_source_arcs():
    xml = notation_xml(
        '<tie type="start"/><notations><tied type="start"/>'
        '<slur type="start" number="2"/></notations>',
        '<tie type="stop"/><notations><tied type="stop"/>'
        '<slur type="stop" number="2"/></notations>')
    arcs = _link(xml)
    assert len(arcs) == 2
    assert {arc.kind for arc in arcs} == {"tie", "slur"}
    for arc in arcs:
        assert (arc.start_source_id, arc.stop_source_id) == (
            "xml-p0-m0-e1","xml-p0-m1-e0")
        assert (arc.start_beat,arc.stop_beat) == (0,4)
        assert arc.issue is None
        assert arc.crosses(4)
        assert not arc.crosses(0)
        assert not arc.crosses(5)
    assert next(a for a in arcs if a.kind == "tie").pitch == ("C","0","4")


def test_partial_window_keeps_unpaired_stop_and_refuses_crossing_cut():
    xml = notation_xml('<notations><slur type="start" number="3"/></notations>',
                       '<notations><slur type="stop" number="3"/></notations>')
    fragment = _link(xml,first=2,last=2,grid=(4,8))
    assert len(fragment) == 1
    assert fragment[0].issue == "unpaired-stop"
    assert fragment[0].start_source_id is None
    assert fragment[0].stop_source_id == "xml-p0-m1-e0"
    assert fragment[0].crosses(4)
    assert not fragment[0].crosses(6)


def test_duplicate_starts_and_unknown_continuations_fail_closed():
    xml = notation_xml(
        '<notations><slur type="start" number="7"/>'
        '<slur type="start" number="7"/>'
        '<slur type="continue" number="9"/></notations>')
    links = _link(xml)
    assert any(a.issue == "unsupported-mark:continue" for a in links)
    assert any(a.issue == "unpaired-start" for a in links)
    assert all(a.crosses(4) for a in links)


def test_same_number_is_scoped_by_independent_source_voice_and_part():
    xml = """<score-partwise><part id="P">
      <measure number="1"><attributes><divisions>1</divisions></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration><voice>1</voice>
        <notations><slur type="start" number="1"/></notations></note>
      <note><pitch><step>D</step><octave>4</octave></pitch>
        <duration>1</duration><voice>1</voice>
        <notations><slur type="stop" number="1"/></notations></note>
      <backup><duration>2</duration></backup>
      <note><pitch><step>E</step><octave>4</octave></pitch>
        <duration>1</duration><voice>2</voice>
        <notations><slur type="start" number="1"/></notations></note>
      <note><pitch><step>F</step><octave>4</octave></pitch>
        <duration>1</duration><voice>2</voice>
        <notations><slur type="stop" number="1"/></notations></note>
      </measure></part></score-partwise>"""
    arcs = _link(xml,first=1,last=1,grid=(0,4))
    assert len(arcs) == 2
    assert {arc.voice_id for arc in arcs} == {
        "xml-p0-s1-v1","xml-p0-s1-v2"}
    assert {tuple((arc.start_beat,arc.stop_beat)) for arc in arcs} == {(0,1)}
    assert all(not arc.crosses(3) for arc in arcs)


def test_inner_source_notes_cannot_be_retimed_or_chordified_under_slur():
    notes = tuple(Note(float(i),float(i+1),60+i,0,0,"right",
                       f"xml-p0-m0-e{i}","xml-p0-s1-v1") for i in range(6))
    xml_notes = []
    for i in range(6):
        slur = ('<notations><slur type="start" number="2"/></notations>' if i==1 else
                '<notations><slur type="stop" number="2"/></notations>' if i==4 else '')
        xml_notes.append(
            f'<note><pitch><step>{"CDEFGAB"[i]}</step><octave>4</octave></pitch>'
            f'<duration>1</duration><voice>1</voice>{slur}</note>')
    xml = '<score-partwise><part id="P"><measure number="1">'+''.join(xml_notes)+'</measure></part></score-partwise>'
    variant=ExerciseVariant("original",Phrase(1,1,1,0,6,notes),tuple(range(6)))
    matrix=MatrixScore.from_phrase(variant.phrase,boundaries=(0,6),
                                    source_musicxml=xml)
    assert {f"xml-p0-m0-e{i}" for i in range(1,5)} == matrix.connector_protected_source_ids()
    dotted = ResearchPolyphonicDottedRhythm().transform(
        variant,boundaries=(0,6),source_musicxml=xml)
    assert not dotted.decisions
    assert dotted.timing.exercise_phrase.notes == variant.notes
    chords=PolyphonicChordifier().transform(
        variant,boundaries=(0,6),source_musicxml=xml)
    assert not chords.decisions


def test_real_musicxml_source_arcs_resolve_without_changing_source_inventory():
    path=Path(__file__).parent/"fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml"
    piece=load_musicxml(path,bpm=80)
    phrase=Phrase(1,1,len(piece.bar_boundaries)-1,
                  piece.bar_boundaries[0],piece.bar_boundaries[-1],piece.notes)
    matrix=MatrixScore.from_phrase(phrase,boundaries=piece.bar_boundaries,
                                    source_musicxml=piece.source_musicxml)
    before=tuple(matrix.notation_elements)
    arcs=matrix.source_connectors()
    assert arcs
    assert any(link.kind == "tie" for link in arcs)
    assert all(link.start_source_id in {s.source_id for s in before} or
               link.start_source_id is None for link in arcs)
    assert all(link.stop_source_id in {s.source_id for s in before} or
               link.stop_source_id is None for link in arcs)
    assert matrix.notation_elements == before
    matrix.verify_lossless()

def test_uncertain_connector_mark_protects_entire_voice_not_just_prior_notes():
    xml = """<score-partwise><part id="P"><measure number="1">
        <note><pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration><voice>1</voice>
        <notations><slur type="continue" number="3"/></notations></note>
        <note><pitch><step>D</step><octave>4</octave></pitch>
        <duration>1</duration><voice>1</voice></note>
    </measure></part></score-partwise>"""
    elements=source_elements(xml,first_bar=1,last_bar=1,boundaries=(0,4))
    links=link_source_connectors(elements)
    assert len(links) == 1
    assert links[0].issue == "unsupported-mark:continue"
    assert protected_connector_source_ids(elements,links) == {
        "xml-p0-m0-e0","xml-p0-m0-e1"}


def test_source_connector_protection_isolates_independent_voice_and_hand():
    xml = """<score-partwise><part id="P"><measure number="1">
        <note><pitch><step>C</step><octave>4</octave></pitch>
          <duration>1</duration><voice>1</voice>
          <notations><slur type="start" number="1"/></notations></note>
        <note><pitch><step>D</step><octave>4</octave></pitch>
          <duration>1</duration><voice>1</voice>
          <notations><slur type="stop" number="1"/></notations></note>
        <backup><duration>2</duration></backup>
        <note><pitch><step>E</step><octave>3</octave></pitch>
          <duration>1</duration><voice>2</voice></note>
        <note><pitch><step>F</step><octave>3</octave></pitch>
          <duration>1</duration><voice>2</voice></note>
    </measure></part></score-partwise>"""
    notes = (
        Note(0,1,60,0,0,"right","xml-p0-m0-e0","xml-p0-s1-v1"),
        Note(1,2,62,0,0,"right","xml-p0-m0-e1","xml-p0-s1-v1"),
        Note(0,1,52,1,0,"left","xml-p0-m0-e3","xml-p0-s1-v2"),
        Note(1,2,53,1,0,"left","xml-p0-m0-e4","xml-p0-s1-v2"))
    variant = ExerciseVariant("original",Phrase(1,1,1,0,4,notes),
                              tuple(range(4)))
    matrix=MatrixScore.from_phrase(variant.phrase,boundaries=(0,4),
                                    source_musicxml=xml)
    assert matrix.connector_protected_source_ids() == {
        "xml-p0-m0-e0","xml-p0-m0-e1"}
    dotted=ResearchPolyphonicDottedRhythm().transform(
        variant,boundaries=(0,4),source_musicxml=xml)
    assert len(dotted.decisions) == 1
    assert dotted.decisions[0].voice == "xml-p0-s1-v2"
    assert dotted.timing.exercise_phrase.notes[:2] == notes[:2]
    assert dotted.timing.exercise_phrase.notes[3].start == pytest.approx(1.5)

"""Two-clock source-tie contract, including corrupted generated notation."""
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.exercise_contracts import OriginalTiming, TimingPlan
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score, infer_piece_clefs
from piano_teacher.research.coda_score_projection import project_coda_score
from piano_teacher.research.coda_written_tie_segments import (
    tie_segment_chains, verify_written_tie_projection,
)

SOURCE=Path(__file__).parent/"fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml"


def _stage(shorten=False):
    piece=load_musicxml(SOURCE,bpm=80)
    original=ExerciseVariant(
        "original",Phrase(1,1,2,0,8,piece.notes),
        tuple(range(len(piece.notes))))
    unchanged=OriginalTiming().transform(original)
    events=list(unchanged.events)
    if shorten:
        index=next(i for i,n in enumerate(original.notes)
                   if n.voice.endswith("-v1") and n.start==0)
        events[index]=replace(events[index],exercise_end=5.5)
    plan=TimingPlan("source-written-ties",original,tuple(events),8)
    stage=project_coda_score(piece,plan,reference_family="dotted-rhythms",bpm=80)
    return piece,stage


def _lesson(stage):
    return build_lesson_score(
        stage.variant.phrase,boundaries=stage.piece.bar_boundaries,
        time_signatures=stage.piece.time_signatures,
        key_signatures=stage.piece.key_signatures,
        clef_changes=stage.piece.clef_changes,
        default_clefs=infer_piece_clefs(stage.piece.notes),
        source_musicxml=stage.piece.source_musicxml,
        retimed_source=True)


@pytest.mark.parametrize("shorten", [False,True])
def test_written_ties_have_distinct_source_segments_and_one_sounding_id(shorten):
    piece,stage=_stage(shorten)
    chains=stage.written_ties
    assert len(chains)==2
    assert len({c.sounding_id for c in chains})==2
    assert {c.pitch for c in chains}=={60}
    assert {c.voice for c in chains}=={
        "xml-p0-s1-v1","xml-p0-s1-v2"}
    assert {c.source_segments[1].written_id for c in chains}.isdisjoint(
        {c.sounding_id for c in chains})
    assert {c.source_segments[0].end for c in chains}=={4}
    assert all(c.source_segments[1].onset==4 for c in chains)
    assert len(stage.variant.notes)==len(piece.notes)==2
    lead=next(c for c in chains if c.voice.endswith("-v1"))
    assert lead.sounding_ends==(6,5.5 if shorten else 6)
    assert len(lead.projected_segments)==2
    lesson=_lesson(stage)
    verify_written_tie_projection(chains,lesson)
    bindings=[x for x in lesson.note_bindings.values()
              if x["source_id"]==lead.sounding_id]
    assert sorted(x["is_attack"] for x in bindings)==[False,True]


def test_written_tie_rejects_generated_retrigger_and_wrong_tie_role():
    _,stage=_stage()
    lesson=_lesson(stage)
    first=stage.written_ties[0]
    glyph=next((ident for ident,binding in lesson.note_bindings.items()
                if binding["source_id"]==first.sounding_id
                and not binding["is_attack"]))
    bindings={k:dict(v) for k,v in lesson.note_bindings.items()}
    bindings[glyph]["is_attack"]=True
    with pytest.raises(ValueError,match="sounding owner"):
        verify_written_tie_projection(
            stage.written_ties,replace(lesson,note_bindings=bindings))
    root=ET.fromstring(lesson.musicxml)
    mark=root.find(f".//note[@id='{glyph}']/notations/tied")
    assert mark is not None
    mark.set("type","start")
    with pytest.raises(ValueError,match="sounding owner"):
        verify_written_tie_projection(
            stage.written_ties,
            replace(lesson,musicxml=ET.tostring(root,encoding="unicode")))


def test_written_tie_rejects_unowned_source_continuation():
    piece,stage=_stage()
    original=stage.timing.original
    broken=replace(original,phrase=replace(
        original.phrase,notes=tuple(n for n in original.notes
                                    if n.voice.endswith("-v1"))))
    reduced=OriginalTiming().transform(broken)
    with pytest.raises(ValueError,match="sounding source attack"):
        tie_segment_chains(piece,reduced)

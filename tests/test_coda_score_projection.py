"""Bounded genuine MusicXML → Coda score, Listen, and MIDI grade.

All three objects share one TimingPlan; original Piece/mastery remains
immutable. The test verifies real MusicXML notes, authored rests,
source context and deliberately damaged source markup rejection.
"""
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.application.listen_session import ListenSession
from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.demo import DemoAudio
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.practice import PlayedNote
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.research.coda_reference_exercises import (
    CodaReferenceChordification, CodaReferenceDotted, CodaReferenceSlowdown,
)
from piano_teacher.research.coda_score_projection import project_coda_score


SOURCE=Path(__file__).parent/"fixtures/research/coda_four_families.musicxml"


def context():
    original=load_musicxml(SOURCE,bpm=80)
    phrase=Phrase(1,1,2,0,8,original.notes)
    variant=ExerciseVariant("original",phrase,tuple(range(len(phrase.notes))))
    return original,variant


class Capture:
    def __init__(self,path):
        self.path=path
        self.calls=[]

    def render(self,variant,bpm):
        self.calls.append((variant,bpm))
        return DemoAudio(self.path,variant.phrase.end*60/bpm,
                         0,8000,"fake-reference-sample")


@pytest.mark.parametrize("kind",["dotted-long","dotted-short","chord","slow-2","slow-4"])
def test_coda_transformed_musicxml_listen_and_grading_share_clock(kind,tmp_path):
    original,variant=context()
    if kind.startswith("slow"):
        factor=int(kind[-1])
        result=CodaReferenceSlowdown(factor).transform(variant)
        family="tempo-shaping"
    elif kind=="chord":
        result=CodaReferenceChordification(8).transform(
            variant,boundaries=original.bar_boundaries,quantization=4,
            source_musicxml=original.source_musicxml)
        family="chordification"
    else:
        result=CodaReferenceDotted(kind=="dotted-long").transform(
            variant,boundaries=original.bar_boundaries,quantization=4,
            source_musicxml=original.source_musicxml)
        family="dotted-rhythms"
    assert result.timing.exercise_phrase.notes!=variant.notes
    stage=project_coda_score(original,result.timing,reference_family=family,
                             bpm=80,revision=8)
    assert stage.original_piece is original
    assert stage.timing.original==variant
    assert stage.piece is not original
    assert ET.tostring(ET.fromstring(original.source_musicxml)) == (
        ET.tostring(ET.fromstring(SOURCE.read_text())))
    assert stage.selection.transformed_rhythm
    assert stage.piece.bar_boundaries[-1]==result.timing.duration_beats
    assert len(stage.piece.bar_boundaries)==(5 if kind=="slow-2"
                                              else 9 if kind=="slow-4" else 3)
    assert stage.tempo_map.duration_beats==result.timing.duration_beats

    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"projection-cache"))
    xml=artifacts.notation_musicxml(stage.selection)
    root=ET.fromstring(xml)
    assert root.tag=="score-partwise"
    assert len(root.findall("part"))==2
    assert len(root.findall(".//part/measure"))==len(stage.piece.bar_boundaries[:-1])*2
    model=artifacts.source_model(stage.selection)
    by_id={item["id"]:item for item in model["notes"]}
    assert set(by_id)=={n.source_id for n in original.notes}
    assert len(by_id)==16
    assert model["duration_beats"]==stage.tempo_map.duration_beats
    for note in stage.variant.notes:
        assert by_id[note.source_id]["onset_beats"]==pytest.approx(note.start)
        assert by_id[note.source_id]["duration_beats"]==pytest.approx(note.end-note.start)
    attacks={symbol["source_id"] for symbol in model["notation_events"]
             if symbol["kind"]=="note" and symbol["is_attack"]}
    assert attacks==set(by_id)
    assert any(symbol["kind"]=="rest" for symbol in model["notation_events"])
    # A key alteration authored at the start of the second source measure
    # survives where that same musical change now occurs, after x2/x4
    # source-to-exercise time expansion.
    second_source_beat=4*(int(kind[-1]) if kind.startswith("slow") else 1)
    assert any(
        any(abs(m["start_beat"]-second_source_beat)<1e-7
            and m["keys"].get("right")==-1 for m in model["measures"])
        for _ in (0,)
    )
    assert stage.piece.source_musicxml != ""  # explicit authored rests retained
    assert ET.tostring(ET.fromstring(original.source_musicxml)) == (
        ET.tostring(ET.fromstring(SOURCE.read_text())))

    played=[PlayedNote(note.pitch,stage.tempo_map.seconds_at(note.start),
                       stage.tempo_map.seconds_at(note.end))
            for note in stage.variant.notes]
    assessment=stage.grade(played,hand="both")
    assert assessment.assessment.clean
    assert {n.note.source_id for n in assessment.assessment.notes}==set(by_id)

    capturer=Capture(tmp_path/"audio.wav")
    listen=ListenSession(tmp_path/"rendered",cache=capturer)
    token=listen.prepare(stage.listen_selection())
    listen.thread.join(timeout=2)
    assert not listen.thread.is_alive()
    assert listen.snapshot()["audio_available"]
    assert listen.snapshot()["duration_seconds"]==pytest.approx(
        stage.tempo_map.duration_seconds)
    assert listen.snapshot()["canonical_source_ids"]==[
        note.source_id for note in original.notes]
    (rendered,bpm),=capturer.calls
    assert bpm==80
    for actual,source in zip(rendered.notes,stage.variant.notes):
        assert actual.source_id==source.source_id
        assert actual.start==pytest.approx(source.start)
        assert actual.end==pytest.approx(source.end)


def test_coda_score_rejects_unsupported_annotations_without_silent_omission():
    original,variant=context()
    result=CodaReferenceDotted(True).transform(
        variant,boundaries=original.bar_boundaries,quantization=4,
        source_musicxml=original.source_musicxml)
    decorated=original.source_musicxml.replace(
        "<type>quarter</type>","<type>quarter</type><notations><articulations><staccato/></articulations></notations>",1)
    with pytest.raises(ValueError,match="expressive/tuplet/tied"):
        project_coda_score(replace(original,source_musicxml=decorated),
                           result.timing,reference_family="dotted-rhythms",bpm=80)
    augmented=original.source_musicxml.replace(
        "</measure>","<direction><direction-type><words>dolce</words></direction-type></direction></measure>",1)
    with pytest.raises(ValueError,match="cannot preserve direction"):
        project_coda_score(replace(original,source_musicxml=augmented),
                           result.timing,reference_family="dotted-rhythms",bpm=80)


def test_coda_score_rejects_wrong_source_grid_and_mastery_overwrites():
    original,variant=context()
    result=CodaReferenceSlowdown(2).transform(variant)
    with pytest.raises(ValueError,match="whole original selected score"):
        project_coda_score(
            original,replace(result.timing,original=replace(
                variant,phrase=replace(variant.phrase,first_bar=2))),
            reference_family="tempo-shaping",bpm=80)
    no_source=replace(original,source_musicxml="")
    with pytest.raises(ValueError,match="original source MusicXML"):
        project_coda_score(no_source,result.timing,
                           reference_family="tempo-shaping",bpm=80)

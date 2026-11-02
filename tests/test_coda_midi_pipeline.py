"""True MIDI input through Coda research -> native SVG / Listen / MIDI grader.

Generated MusicXML is an internal notation format, never an input
requirement. This proof uses actual SMF files, original PPQ, production
engraving/audio, and the same transformed source IDs in software grading.
Physical keyboard and native graphical Godot remain separate.
"""
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET
import wave

import pytest

from piano_teacher.application.listen_session import ListenSession
from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.demo import DemoAudioCache
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.live_input_view import LiveInputView
from piano_teacher.music import Phrase, load_midi
from piano_teacher.practice import PlayedNote
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.research.coda_midi_grid import midi_coda_quantization
from piano_teacher.research.coda_reference_exercises import (
    CodaReferenceSlowdown,CodaReferenceDotted,CodaReferenceChordification,
)
from piano_teacher.research.coda_score_projection import project_coda_score


ROOT=Path(__file__).parent/"fixtures/musical_fidelity"


def _midi_original(filename):
    piece=load_midi(ROOT/filename)
    phrase=Phrase(1,1,len(piece.bar_boundaries)-1,0,
                  piece.bar_boundaries[-1],piece.notes)
    variant=ExerciseVariant("midi-source",phrase,
                            tuple(range(len(phrase.notes))))
    return piece,variant


def _stage(filename,kind):
    piece,variant=_midi_original(filename)
    if kind=="slow":
        result=CodaReferenceSlowdown(2).transform(variant)
        family="tempo-shaping"
    elif kind=="dotted":
        result=CodaReferenceDotted(True).transform(
            variant,boundaries=piece.bar_boundaries,
            quantization=midi_coda_quantization(
                piece,variant.phrase,dotted=True),
            source_musicxml="")
        family="dotted-rhythms"
    else:
        q=midi_coda_quantization(piece,variant.phrase)
        result=CodaReferenceChordification(2*q).transform(
            variant,boundaries=piece.bar_boundaries,
            quantization=q,source_musicxml="")
        family="chordification"
    return piece,variant,project_coda_score(
        piece,result.timing,reference_family=family,bpm=piece.bpm)


@pytest.mark.parametrize(("filename","kind"),[
    ("midi_four_four.mid","slow"),
    ("midi_four_four.mid","dotted"),
    ("midi_four_four.mid","chord"),
    ("midi_three_four.mid","slow"),
    ("midi_mixed_meter.mid","slow"),
    ("midi_sparse_rests.mid","slow"),
    ("midi_triplets.mid","slow"),
])
def test_midi_coda_transformation_engraves_and_grades_identical_ids(
    filename,kind,tmp_path
):
    piece,original,stage=_stage(filename,kind)
    assert piece.source_musicxml==""
    assert piece.source_format=="midi"
    assert piece.midi_ticks_per_beat>0
    assert stage.original_piece is piece
    assert piece.notes==original.notes
    assert stage.original_piece.source_musicxml==""
    assert stage.piece.source_musicxml==""   # no fake authored source
    assert stage.timing.original is original or (
        stage.timing.original.notes==original.notes)
    assert stage.selection.transformed_rhythm
    assert len(stage.original_source_sha256)==64
    assert stage.original_source_sha256!=sha256(b"").hexdigest()
    assert stage.tempo_map.duration_beats==pytest.approx(stage.timing.duration_beats)

    expected={n.source_id for n in original.notes}
    transformed={n.source_id for n in stage.variant.notes}
    assert expected==transformed and len(expected)==len(original.notes)
    assert all(n.start>=0 and n.end<=stage.variant.phrase.end+1e-7
               for n in stage.variant.notes)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"notation"))
    xml=artifacts.notation_musicxml(stage.selection)
    assert "<score-partwise" in xml
    assert len(ET.fromstring(xml).findall("part"))==2
    engraving=artifacts.engraving(stage.selection)
    assert engraving.pages
    assert set(engraving.layout["attack_map"])==expected
    assert engraving.layout["beats"]==pytest.approx(
        stage.tempo_map.duration_beats)
    assert {x["source_id"] for x in engraving.layout["notes"]
            if x.get("is_attack")}==expected
    for svg in engraving.pages:
        element=ET.fromstring(svg)
        assert element.tag.endswith("svg")
        assert len(list(element.iter()))>60

    played=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                       stage.tempo_map.seconds_at(n.end))
            for n in stage.variant.notes]
    outcome=stage.grade(played)
    assert outcome.assessment.clean
    assert {n.note.source_id for n in outcome.assessment.notes}==expected


def test_midi_rhythm_drill_really_changes_source_and_listen_uses_same_clock(tmp_path):
    piece,original,stage=_stage("midi_four_four.mid","dotted")
    assert [(n.start,n.end) for n in stage.variant.notes] != [
        (n.start,n.end) for n in original.notes]
    cache=DemoAudioCache(tmp_path/"midi-coda-wav",sample_rate=8000)
    listening=ListenSession(tmp_path/"midi-coda-wav",cache=cache)
    token=listening.prepare(stage.listen_selection())
    listening.thread.join(timeout=8)
    assert not listening.thread.is_alive()
    assert listening.take_failure() is None
    assert listening.snapshot()["audio_available"]
    assert listening.snapshot()["canonical_source_ids"]==[
        n.source_id for n in original.notes]
    assert listening.snapshot()["duration_seconds"]==pytest.approx(
        stage.tempo_map.duration_seconds)
    with wave.open(str(listening.audio_path(token)),"rb") as wav:
        assert wav.getframerate()==8000
        assert wav.getnframes()/8000==pytest.approx(
            stage.tempo_map.duration_seconds,abs=.00013)

    first=stage.variant.notes[0]
    live=LiveInputView()
    live.receive(
        pitch=first.pitch,is_on=True,
        now=100+stage.tempo_map.seconds_at(first.start),
        phrase=stage.variant.phrase,hand=first.hand,
        bpm=piece.bpm,from_beat=0,run_at=100,running=True,
        paused=False,preview=False,mode="practice",transport_id=47,
        tempo_map=stage.tempo_map)
    assert live.events[-1]["source_id"]==first.source_id
    assert live.events[-1]["status"]=="on_time"


def test_distinct_midi_inputs_have_distinct_source_timeline_fingerprints():
    _,_,one=_stage("midi_four_four.mid","slow")
    _,_,two=_stage("midi_three_four.mid","slow")
    assert one.original_source_sha256!=two.original_source_sha256
    assert one.selection.fingerprint!=two.selection.fingerprint

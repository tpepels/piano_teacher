"""Selected non-first MIDI measure through real SVG, WAV, grading/feedback.

The imported whole piece is immutable. The exercise score uses local beat
zero; original MIDI attack IDs and absolute beat coordinates stay available
to the selector for progress/mastery tracking.
"""
from pathlib import Path
from xml.etree import ElementTree as ET
import wave

import pytest

from piano_teacher.application.listen_session import ListenSession
from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.demo import DemoAudioCache
from piano_teacher.live_input_view import LiveInputView
from piano_teacher.music import load_midi
from piano_teacher.practice import PlayedNote
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.research.coda_midi_passage import project_midi_passage


FIXTURE=Path(__file__).parent/"fixtures/musical_fidelity/midi_three_four.mid"


def test_later_midi_measure_real_engraving_listen_and_midi_feedback(tmp_path):
    piece=load_midi(FIXTURE)
    before=tuple(piece.notes)
    selected,stage=project_midi_passage(
        piece,2,2,family="tempo-shaping",slowdown_factor=2,revision=7)
    assert stage.original_piece is selected.piece
    assert piece.notes==before
    assert selected.source_start==3
    assert selected.first_bar==2
    assert selected.original_coordinates()
    assert stage.variant.phrase.start==0
    assert stage.variant.phrase.end==6
    expected={n.source_id for n in selected.variant.notes}

    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"source"))
    xml=artifacts.notation_musicxml(stage.selection)
    assert "<score-partwise" in xml
    model=artifacts.source_model(stage.selection)
    assert {n["id"] for n in model["notes"]}==expected
    assert model["duration_beats"]==pytest.approx(6)
    engraved=artifacts.engraving(stage.selection)
    assert engraved.pages
    assert set(engraved.layout["attack_map"])==expected
    assert engraved.layout["beats"]==pytest.approx(6)
    assert all(ET.fromstring(svg).tag.endswith("svg") for svg in engraved.pages)

    audio=DemoAudioCache(tmp_path/"audio",sample_rate=8000)
    listen=ListenSession(tmp_path/"audio",cache=audio)
    token=listen.prepare(stage.listen_selection())
    listen.thread.join(timeout=8)
    assert not listen.thread.is_alive()
    assert listen.take_failure() is None
    assert listen.snapshot()["canonical_source_ids"]==[
        n.source_id for n in selected.variant.notes]
    with wave.open(str(listen.audio_path(token)),"rb") as wav:
        assert wav.getnframes()/wav.getframerate()==pytest.approx(
            stage.tempo_map.duration_seconds,abs=.00013)

    performed=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                          stage.tempo_map.seconds_at(n.end))
               for n in stage.variant.notes]
    assert stage.grade(performed).assessment.clean
    first=stage.variant.notes[0]
    view=LiveInputView()
    view.receive(pitch=first.pitch,is_on=True,
                 now=100+stage.tempo_map.seconds_at(first.start),
                 phrase=stage.variant.phrase,hand=first.hand,bpm=piece.bpm,
                 from_beat=0,run_at=100,running=True,paused=False,
                 preview=False,mode="practice",transport_id=8,
                 tempo_map=stage.tempo_map)
    assert view.recent[-1]["status"]=="on_time"
    assert view.recent[-1]["source_id"]==first.source_id

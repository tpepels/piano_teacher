"""Selected wider-repertoire Coda notation, Listen, MIDI grading proof.

Runs actual MusicXML->source import->Coda timing->Verovio SVG->WAV
and software MIDI evaluation. This is NOT a physical keyboard or Godot
framebuffer test and does not establish original author's annotation parity.
"""
from pathlib import Path
from xml.etree import ElementTree as ET
import wave

import pytest

from piano_teacher.application.listen_session import ListenSession
from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.demo import DemoAudioCache
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.live_input_view import LiveInputView
from piano_teacher.music import Phrase
from piano_teacher.practice import PlayedNote
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.research.coda_reference_exercises import CodaReferenceSlowdown
from piano_teacher.research.coda_score_projection import project_coda_score


ROOT = Path(__file__).parent / "fixtures/musical_fidelity"


@pytest.mark.parametrize("source", ["xml_mixed_meter.musicxml",
                                   "xml_trailing_rests.musicxml"])
def test_real_coda_slowdown_source_score_listen_and_grader_share_clock(
    source, tmp_path
):
    original_piece = load_musicxml(ROOT / source, bpm=72)
    original_xml = original_piece.source_musicxml
    original_notes = original_piece.notes
    grid = original_piece.bar_boundaries
    phrase = Phrase(1,1,len(grid)-1,0,grid[-1],original_notes)
    variant = ExerciseVariant("original",phrase,tuple(range(len(original_notes))))
    timing = CodaReferenceSlowdown(2).transform(variant).timing
    stage = project_coda_score(
        original_piece,timing,reference_family="tempo-shaping",bpm=72)
    assert stage.original_piece is original_piece
    assert original_piece.source_musicxml == original_xml
    assert original_piece.notes == original_notes
    assert stage.piece.bar_boundaries[-1] == pytest.approx(grid[-1]*2)
    expected = {n.source_id for n in original_notes}
    assert len(expected) == len(original_notes)

    artifacts = ScoreArtifacts(PreprocessingCache(tmp_path/"score"))
    engraving = artifacts.engraving(stage.selection)
    assert engraving.pages and len(engraving.pages) <= 8
    assert set(engraving.layout["attack_map"]) == expected
    assert engraving.layout["beats"] == pytest.approx(
        stage.tempo_map.duration_beats)
    for svg in engraving.pages:
        root = ET.fromstring(svg)
        assert root.tag.endswith("svg")
        assert len(list(root.iter())) > 60
    notation_xml = artifacts.notation_musicxml(stage.selection)
    assert "<score-partwise" in notation_xml
    # Distinct original attacks must never disappear or be duplicated
    # when the notation is split into written noteheads or ties.
    assert {n["source_id"] for n in engraving.layout["notes"]
            if n.get("is_attack")} == expected

    cache = DemoAudioCache(tmp_path/"demo",sample_rate=8000)
    listening = ListenSession(tmp_path/"demo",cache=cache)
    token = listening.prepare(stage.listen_selection())
    listening.thread.join(timeout=8)
    assert not listening.thread.is_alive()
    assert listening.take_failure() is None
    assert listening.snapshot()["audio_available"]
    assert listening.snapshot()["duration_seconds"] == pytest.approx(
        stage.tempo_map.duration_seconds)
    with wave.open(str(listening.audio_path(token)), "rb") as wav:
        assert wav.getframerate() == 8000
        assert wav.getnframes()/8000 == pytest.approx(
            stage.tempo_map.duration_seconds,abs=.00013)

    notes = stage.variant.notes
    played = [PlayedNote(
        n.pitch, stage.tempo_map.seconds_at(n.start),
        stage.tempo_map.seconds_at(n.end)) for n in notes]
    assert stage.grade(played).assessment.clean
    # The live input presentation uses the same transformed score identity
    # and beat seconds as the playback and grader.
    first = notes[0]
    live = LiveInputView()
    live.receive(
        pitch=first.pitch,is_on=True,
        now=100+stage.tempo_map.seconds_at(first.start),
        phrase=stage.variant.phrase,hand=first.hand,bpm=72,from_beat=0,
        run_at=100,running=True,paused=False,preview=False,
        mode="practice",transport_id=41,tempo_map=stage.tempo_map)
    assert live.events[-1]["source_id"] == first.source_id
    assert live.events[-1]["status"] == "on_time"

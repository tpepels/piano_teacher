"""Real native engraving and playback for the Coda full-score catalog adapter.

The author defines exercise categories but no training sequence. Verify our
MIDI exercise alternatives still use ordinary Verovio/Listen/graded stages.
"""
from pathlib import Path
from xml.etree import ElementTree as ET
import pytest

from piano_teacher.application.listen_session import ListenSelection,ListenSession
from piano_teacher.application.score_artifacts import ScoreArtifacts,ScoreSelection
from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.assessment_clock import expected_note_seconds
from piano_teacher.practice import PlayedNote,evaluate


ROOT=Path(__file__).parent/"fixtures/musical_fidelity"


@pytest.mark.parametrize("name",["midi_four_four.mid","midi_three_four.mid"])
@pytest.mark.parametrize("factor",[2,4])
def test_full_excerpt_source_identity_engraving_and_slowdown(name,factor,tmp_path):
    piece=load_midi(ROOT/name)
    plan=LearningPlan(piece,exercise_strategy="coda-midi")
    assert plan.exercises[0].phrase.notes==piece.notes
    index=next(i for i,stage in enumerate(plan.stages)
               if stage.variant.level==f"coda-slowdown-x{factor}")
    plan.variant_index=index
    stage=plan.active_stage
    tempo=stage.tempo_map(120)
    assert tempo is not None
    assert tempo.bpm_at(0)==pytest.approx(120/factor)
    assert stage.variant.notes==piece.notes

    selected=ScoreSelection(
        piece=piece,phrase=stage.variant.phrase,hand=plan.hand,
        stage_key=plan.identity,revision=2,fingerprint="coda-full-score",
        transformed_rhythm=stage.transformed_rhythm)
    score=ScoreArtifacts(PreprocessingCache(tmp_path/"score"))
    engraved=score.engraving(selected)
    ids={n.source_id for n in stage.variant.notes}
    assert set(engraved.layout["attack_map"])==ids
    assert all(ET.fromstring(page).tag.endswith("svg") for page in engraved.pages)

    listening=ListenSession(tmp_path/"listen")
    try:
        token=listening.prepare(ListenSelection(
            variant=stage.variant,bpm=120,stage_key=plan.identity,
            revision=2,bar_boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures,tempo_map=tempo))
        listening.thread.join(timeout=8)
        assert not listening.thread.is_alive()
        assert listening.take_failure() is None
        assert listening.snapshot()["audio_available"]
        assert listening.snapshot()["duration_seconds"]==pytest.approx(
            tempo.duration_seconds)
    finally:
        listening.cancel()

    expected=expected_note_seconds(stage.variant.phrase,tempo)
    played=[PlayedNote(note.pitch,*expected(note)[:2])
            for note in stage.variant.notes]
    assert evaluate(stage.variant.phrase,plan.hand,plan.bpm,played,
                    expected_seconds=expected).clean

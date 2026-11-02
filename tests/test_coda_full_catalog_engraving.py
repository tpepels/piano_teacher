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


@pytest.mark.parametrize("family", ("coda-dotted-", "coda-chord-"))
def test_actual_sparse_coda_rhythm_stage_native_engraving_listen_and_grading(
        family, tmp_path):
    """The *live LearningPlan's* sparse generated steps, not research plans."""
    import mido
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage(
        "track_name", name="Right Hand", time=0))
    track.append(mido.MetaMessage(
        "time_signature", numerator=4, denominator=4, time=0))
    for pitch in range(60, 68):
        track.append(mido.Message(
            "note_on", note=pitch, velocity=80, time=0))
        track.append(mido.Message(
            "note_off", note=pitch, velocity=0, time=240))
    midi.tracks.append(track)
    source = tmp_path / "full-coda-rhythm.mid"
    midi.save(source)

    piece = load_midi(source)
    plan = LearningPlan(piece, exercise_strategy="coda-midi")
    index = next(i for i, stage in enumerate(plan.stages)
                 if stage.variant.level.startswith(family))
    plan.variant_index = index
    stage = plan.active_stage
    assert stage.transformed_rhythm
    original = {n.source_id: n for n in piece.notes}
    notes = stage.variant.notes
    assert {n.source_id for n in notes} == set(original)
    assert len(notes) == len(original)
    assert any((n.start, n.end) !=
               (original[n.source_id].start, original[n.source_id].end)
               for n in notes)
    from piano_teacher.exercise_contracts import ConstantTempo, OriginalTiming
    tempo = (stage.tempo_map(90) or
             ConstantTempo().generate(OriginalTiming().transform(stage.variant), 90))
    selection = ScoreSelection(
        piece=piece, phrase=stage.variant.phrase, hand=plan.hand,
        stage_key=plan.identity, revision=8, fingerprint="sparse-coda-rhythm",
        transformed_rhythm=stage.transformed_rhythm)
    artifacts = ScoreArtifacts(PreprocessingCache(tmp_path / "score"))
    engraved = artifacts.engraving(selection)
    assert set(engraved.layout["attack_map"]) == set(original)
    assert all(ET.fromstring(page).tag.endswith("svg") for page in engraved.pages)

    listening = ListenSession(tmp_path / "listen")
    try:
        listening.prepare(ListenSelection(
            variant=stage.variant, bpm=90, stage_key=plan.identity,
            revision=8, bar_boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures, tempo_map=tempo))
        listening.thread.join(timeout=8)
        assert not listening.thread.is_alive()
        assert listening.take_failure() is None
        assert listening.snapshot()["audio_available"]
    finally:
        listening.cancel()
    expected = expected_note_seconds(stage.variant.phrase, tempo)
    played = [PlayedNote(n.pitch, *expected(n)[:2]) for n in notes]
    assert evaluate(stage.variant.phrase, plan.hand, plan.bpm, played,
                    expected_seconds=expected).clean

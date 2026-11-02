"""Coda is chosen for one MIDI PIECE, then generates its normal lesson path.

No lesson-level trial plan, source swapping or temporary progress store.
The normal source-piece teaching sequence owns every selected Coda stage.
"""
from pathlib import Path

import mido
import pytest

from piano_teacher.assessment_clock import expected_note_seconds
from piano_teacher.application.score_artifacts import ScoreSelection, ScoreArtifacts
from piano_teacher.application.listen_session import ListenSelection, ListenSession
from piano_teacher.exercise_strategies import available_strategies,resolve_strategy
from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi
from piano_teacher.practice import PlayedNote, evaluate
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.server import PracticeEngine


MIDI=Path(__file__).parent/"fixtures/musical_fidelity/midi_three_four.mid"


def _many_eighths(path: Path):
    mid=mido.MidiFile(type=1,ticks_per_beat=480)
    part=mido.MidiTrack()
    part.append(mido.MetaMessage("track_name",name="Right Hand",time=0))
    part.append(mido.MetaMessage("time_signature",numerator=4,denominator=4,time=0))
    for bar in range(3):
        for i in range(8):
            part.append(mido.Message("note_on",note=60+(i%5),velocity=90,time=0))
            part.append(mido.Message("note_off",note=60+(i%5),velocity=0,time=240))
    part.append(mido.MetaMessage("end_of_track",time=0))
    mid.tracks.append(part)
    mid.save(path)


def test_piece_level_coda_is_visible_and_midi_only():
    assert any(x["id"]=="coda-midi" for x in available_strategies())
    assert resolve_strategy("coda-midi",piece=load_midi(MIDI)).name=="coda-midi"
    with pytest.raises(ValueError,match="imported MIDI"):
        resolve_strategy("coda-midi")


def test_whole_piece_coda_plan_has_stages_for_each_lesson_and_original_final(tmp_path):
    filename=tmp_path/"three-bars.mid"
    _many_eighths(filename)
    piece=load_midi(filename)
    plan=LearningPlan(piece,exercise_strategy="coda-midi",consolidate=False)
    assert plan.piece is piece
    assert plan.exercise_strategy.name=="coda-midi"
    assert len(plan.exercises)>=3
    assert plan.exercises[0].phrase.notes!=piece.notes
    assert plan.exercises[0].phrase.first_bar==1
    assert plan.exercises[0].phrase.last_bar<3
    assert plan.exercises[0].key.startswith("coda:excerpt:1-")
    assert plan.exercises[-1].kind=="perform"
    assert plan.exercises[-1].phrase.notes==piece.notes
    steps=plan.lesson_steps
    assert steps and len(steps)>len(plan.exercises)
    assert len({s.key for s in steps})==len(steps)
    assert any(s.level=="coda-slowdown-x2" for s in steps)
    assert any(s.level.startswith("coda-dotted-") for s in steps)
    assert any(s.level.startswith("coda-chord-") for s in steps)
    assert any(s.level=="coda-slowdown-x4" for s in steps)
    for ex in plan.exercises:
        hand="both" if ex.kind != "learn" else "right"
        stages=plan._pipeline_stages(ex,hand)
        assert stages[-1].variant.level=="original"
        baseline_ids={n.source_id for n in stages[-1].variant.notes}
        for stage in stages:
            assert {n.source_id for n in stage.variant.notes} <= baseline_ids
            assert stage.variant.phrase.start==ex.phrase.start
            assert stage.variant.phrase.end==ex.phrase.end
        if ex.kind=="learn":
            assert any(s.variant.level=="coda-slowdown-x2" for s in stages)
        else:
            assert len(stages)==1
    # Version 7 is a different teaching path; earlier v6 whole-score
    # completion records must not confer passage mastery automatically.
    assert all(step.key.startswith("course:8:coda-midi:") for step in steps)


def test_coda_stage_uses_native_score_listen_and_grader_on_original_piece(tmp_path):
    piece=load_midi(MIDI)
    plan=LearningPlan(piece,exercise_strategy="coda-midi",consolidate=False)
    chosen=next(i for i,s in enumerate(plan.variants)
                if s.level=="coda-slowdown-x2")
    plan.variant_index=chosen
    stage=plan.active_stage
    assert stage.shaped_tempo
    assert not stage.transformed_rhythm
    tempo=stage.tempo_map(100)
    assert tempo.bpm_at(0)==pytest.approx(50)
    assert tempo.duration_seconds==pytest.approx(
        (stage.variant.phrase.end-stage.variant.phrase.start)*60/50)
    selection=ScoreSelection(
        piece=piece,phrase=stage.variant.phrase,hand=plan.hand,
        stage_key=plan.identity,revision=3,fingerprint="whole-source",
        transformed_rhythm=stage.transformed_rhythm)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"preprocessed"))
    model=artifacts.source_model(selection)
    assert {x["id"] for x in model["notes"]}=={
        n.source_id for n in stage.variant.notes}
    listen=ListenSession(tmp_path/"audio")
    try:
        selected=ListenSelection(
            variant=stage.variant,bpm=100,stage_key=plan.identity,
            revision=3,bar_boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures,tempo_map=tempo)
        listen.prepare(selected)
        listen.thread.join(timeout=10)
        assert not listen.thread.is_alive()
        assert listen.take_failure() is None
        assert listen.snapshot()["audio_available"]
        assert listen.snapshot()["duration_seconds"]==pytest.approx(
            tempo.duration_seconds)
    finally:
        listen.cancel()
    played=[PlayedNote(note.pitch,tempo.seconds_at(note.start-stage.variant.phrase.start),
                       tempo.seconds_at(note.end-stage.variant.phrase.start))
            for note in stage.variant.notes]
    assert evaluate(stage.variant.phrase,plan.hand,plan.bpm,played,
        expected_seconds=expected_note_seconds(
            stage.variant.phrase,tempo)).clean


def test_engine_changes_strategy_on_loaded_midi_without_swapping_piece(tmp_path):
    engine=PracticeEngine(tmp_path,enable_midi=False)
    try:
        engine.load(str(MIDI))
        source=engine.plan.piece
        fingerprint=engine.fingerprint
        assert engine.plan.exercise_strategy.name=="coda-fukuda-midi"
        assert engine.plan.piece is source
        engine.set_preferences(exercise_strategy="coda-midi")
        first=engine.plan.identity
        engine.set_preferences(exercise_strategy="legacy")
        assert engine.plan.piece is source
        assert engine.fingerprint==fingerprint
        engine.set_preferences(exercise_strategy="coda-midi")
        assert engine.plan.piece is source
        assert engine.fingerprint==fingerprint
        assert engine.plan.identity==first
        engine.control("listen")
        assert engine.listen._selection.stage_key==engine.plan.identity
    finally:
        engine.listen.cancel()
        engine.db.close()


def test_warmups_ignore_selected_midi_piece_strategy():
    from piano_teacher.music import Note,Phrase,Piece
    notes=(Note(0,1,60,0,0,"right"),)
    piece=Piece("Warmup",60,notes,(Phrase(1,1,1,0,4,notes),),
                bar_boundaries=(0,4),time_signatures=((0,4,4),))
    plan=LearningPlan(piece,warmup=True,exercise_strategy="coda-midi")
    assert plan.exercise_strategy.name=="legacy"

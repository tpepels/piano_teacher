"""Prove the selectable Coda/Fukuda course is musically different and wired.

No physical MIDI device or long corpus test is required. The short synthetic
source contains chord simplification, dense attacks, and distinct hand voices.
"""
from dataclasses import replace
from pathlib import Path

import mido
import pytest

from piano_teacher.assessment_clock import expected_note_seconds
from piano_teacher.application.listen_session import ListenSelection, ListenSession
from piano_teacher.practice import PlayedNote, evaluate
from piano_teacher.application.lesson_snapshot import build_lesson_snapshot
from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
from piano_teacher.exercise_pipeline import ExerciseStage
from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_generators import CodaLessonGenerator
from piano_teacher.lesson_stage_semantics import (
    describe, difference, distinct_stages, fingerprint)
from piano_teacher.music import load_midi
from piano_teacher.preprocessing_cache import PreprocessingCache
from stage_fixtures import coda_course, fukuda_course
from piano_teacher.state_projection import (
    ActivitySnapshot, SessionSnapshot, TimingSnapshot, project_session_state)


THREE_FOUR = Path(__file__).parent/"fixtures/musical_fidelity/midi_three_four.mid"


@pytest.fixture
def piece(tmp_path):
    filename = tmp_path / "chords-and-rapid-notes.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    for name, root in (("Right Hand", 60), ("Left Hand", 43)):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=name))
        track.append(mido.MetaMessage("time_signature",
                                      numerator=4, denominator=4, time=0))
        events = []
        for bar in range(4):
            beat = bar * 1920
            for pitch in (root, root + 4, root + 7, root + 12):
                events.extend(((beat, 1, pitch), (beat + 240, 0, pitch)))
            for attack in range(1, 8):
                pitch = root + (attack % 5)
                tick = beat + attack * 240
                events.extend(((tick, 1, pitch), (tick + 240, 0, pitch)))
        cursor = 0
        for tick, on, pitch in sorted(events, key=lambda entry: (entry[0], entry[1])):
            track.append(mido.Message("note_on" if on else "note_off",
                                      note=pitch, velocity=85 if on else 0,
                                      time=tick-cursor))
            cursor = tick
        track.append(mido.MetaMessage("end_of_track", time=7680-cursor))
        midi.tracks.append(track)
    midi.save(filename)
    return load_midi(filename)


def test_noop_aliases_and_duplicate_performances_are_not_teaching_steps(piece):
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    ex = next(ex for ex in plan.exercises if ex.kind == "learn")
    original = plan.lesson_definition.stages(ex, "right")[-1]
    duplicate = ExerciseStage(replace(original.variant, level="editorial-renamed"))
    assert not difference(duplicate, original).meaningful
    assert distinct_stages((duplicate, duplicate), original) == ()
    assert fingerprint(duplicate) == fingerprint(original)
    stages = plan.lesson_definition.stages(ex, "right")
    assert stages[-1].variant.level == "original"
    assert all(difference(s, stages[-1]).meaningful for s in stages[:-1])
    assert len({fingerprint(s) for s in stages}) == len(stages)


def test_hybrid_first_stage_is_a_real_source_bound_reduction(piece):
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    assert plan.exercise.kind == "learn"
    assert plan.active_phrase.last_bar < len(piece.bar_boundaries)-1
    assert plan.active_variant.level.startswith("fukuda-midi-")
    assert any(s.variant.level.startswith("fukuda-midi-")
               for s in plan.stages[:-1])
    assert any(s.variant.level.startswith("coda-")
               for s in plan.stages[:-1])
    delta = difference(plan.active_stage, plan.stages[-1])
    assert delta.removed > 0
    assert 0 < delta.active_count < delta.source_count
    info = describe(plan.active_stage, plan.stages[-1])
    assert info["meaningful"] and info["family"] == "Fukuda"
    assert str(delta.active_count) in info["change"]
    assert set(n.source_id for n in plan.active_variant.notes) < set(
        n.source_id for n in plan.stages[-1].variant.notes)


def test_pure_coda_research_catalog_and_teaching_path_stay_separate(piece):
    author = CodaLessonGenerator().generate(piece)
    application = coda_course(piece)
    assert author.exercises[0].phrase.notes == piece.notes
    assert application.exercises[0].phrase.notes != piece.notes
    assert application.exercises[-1].phrase.notes == piece.notes
    for ex in application.exercises:
        for hand in ex.hands or ("both",):
            stages = application.lesson_definition.stages(ex, hand)
            if ex.kind == "learn":
                assert all(difference(s, stages[-1]).meaningful
                           for s in stages[:-1])
                assert len({fingerprint(s) for s in stages}) == len(stages)
            assert stages[-1].variant.level == "original"


def test_selected_coda_stage_reaches_notation_and_real_tempo_projection(piece, tmp_path):
    plan = coda_course(piece)
    index = next(i for i, stage in enumerate(plan.stages)
                 if stage.variant.level.startswith("coda-slowdown-x2"))
    plan.variant_index = index
    assert plan.active_stage.shaped_tempo
    active = plan.active_stage
    tempo_map = active.tempo_map(plan.bpm)
    assert tempo_map.bpm_at(0) == pytest.approx(plan.bpm / 2)
    selected = ScoreSelection(
        piece=piece, phrase=plan.active_phrase, hand=plan.hand,
        stage_key=plan.identity, revision=3, fingerprint="stage-wire",
        transformed_rhythm=active.transformed_rhythm)
    model = ScoreArtifacts(PreprocessingCache(tmp_path / "cache")).source_model(selected)
    assert {n["id"] for n in model["notes"]} == {
        n.source_id for n in plan.active_variant.notes}
    lesson = build_lesson_snapshot(
        plan, plan.exercise, plan.active_variant, fingerprint="stage-wire",
        warmup=False, lesson_steps=())
    snapshot = SessionSnapshot(
        lesson=lesson, activity=ActivitySnapshot(sampled_at=10),
        timing=TimingSnapshot(sampled_at=10, now=10, run_at=10,
                              practice_timeline={"gap": {"duration_beats": 4}},
                              tempo_segments=tempo_map.as_segments()))
    state = project_session_state(snapshot)
    assert state["stage_family"] == "Coda"
    assert state["stage_label"] == "Slowed playback"
    assert state["stage_change"] == "tempo adjustment"
    assert state["stage_meaningful"] is True
    assert state["bpm"] == plan.bpm
    assert state["effective_bpm"] == pytest.approx(plan.bpm / 2)


def test_already_original_stage_reports_no_invented_technique(piece):
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    plan.variant_index = len(plan.variants)-1
    metadata = describe(plan.active_stage, plan.stages[-1])
    assert metadata["family"] == "Original"
    assert metadata["label"] == "Original notes and rhythm"
    assert not metadata["meaningful"]
    assert metadata["removed"] == metadata["retimed"] == 0


def test_live_engine_state_and_step_overview_show_actual_selected_strategy(piece, tmp_path):
    from piano_teacher.server import PracticeEngine
    engine = PracticeEngine(tmp_path / "engine-data", enable_midi=False)
    try:
        engine.set_preferences(exercise_strategy="coda-fukuda-midi")
        engine.load(str(tmp_path / "chords-and-rapid-notes.mid"))
        state = engine.state()
        assert state["exercise_strategy"] == "coda-fukuda-midi"
        assert state["stage_family"] == "Fukuda"
        assert state["stage_meaningful"]
        assert state["stage_change"] != "unchanged source"
        assert state["last_bar"] < len(piece.bar_boundaries) - 1
        overview = engine.lesson_overview()
        assert overview["exercise_strategy"] == state["exercise_strategy"]
        assert overview["steps"][0]["stage_family"] == state["stage_family"]
        assert overview["steps"][0]["stage_label"] == state["stage_label"]
        assert overview["steps"][0]["stage_change"] == state["stage_change"]
        assert overview["steps"][-1]["stage_family"] == "Original"
        # Removed strategies cannot be selected; the course stays intact.
        identity = engine.plan.identity
        with pytest.raises(ValueError, match="Unknown exercise strategy"):
            engine.set_preferences(exercise_strategy="coda-midi")
        assert engine.plan.identity == identity
        assert engine.state()["exercise_strategy"] == "coda-fukuda-midi"
    finally:
        engine.listen.cancel()
        engine.db.close()


def test_third_party_midi_stage_uses_explicit_metadata_not_level_prefix(piece):
    """An external algorithm must be selectable without any Coda/Fukuda naming."""
    from piano_teacher.exercise_generator import ExerciseVariant
    from piano_teacher.lesson_stage_semantics import teaching_sequence

    baseline = LearningPlan(piece, exercise_strategy="coda-fukuda-midi").stages[-1]
    source = baseline.variant
    subset = source.notes[::2]
    assert len(subset) >= 2
    custom = ExerciseStage(
        ExerciseVariant("opaque-harmonic-7", replace(source.phrase, notes=subset),
                        source.source_indices[::2]),
        origin="third-party-harmony",
        technique="voice-leading",
        display_name="Simplified harmonic skeleton")
    stages = teaching_sequence((custom, baseline))
    assert stages == (custom, baseline)
    report = describe(custom, baseline)
    assert report["origin"] == "third-party-harmony"
    assert report["technique"] == "voice-leading"
    assert report["family"] == "Third Party Harmony"
    assert report["label"] == "Simplified harmonic skeleton"
    assert report["removed"] > 0
    assert report["meaningful"] is True


def test_selected_coda_and_fukuda_stages_publish_generator_owned_metadata(piece):
    for plan in (coda_course(piece), fukuda_course(piece),
                 LearningPlan(piece, exercise_strategy="coda-fukuda-midi")):
        for ex in plan.exercises:
            from piano_teacher.lesson_generators import lesson_hands
            for hand in lesson_hands(ex):
                stages = plan.lesson_definition.stages(ex, hand)
                for stage in stages:
                    if stage.variant.level == "original":
                        assert describe(stage, stages[-1])["family"] == "Original"
                    elif stage.variant.level.startswith("fukuda-midi-"):
                        assert stage.origin == "fukuda-midi"
                        assert stage.technique and stage.display_name
                    elif stage.variant.level.startswith("coda-"):
                        assert stage.origin == "coda-midi"
                        assert stage.technique and stage.display_name
        assert plan.exercises[-1].kind == "perform"
        assert plan.exercises[-1].phrase.notes == piece.notes


def test_third_party_pitch_and_dynamic_exercises_are_not_dropped_as_noops(piece):
    from piano_teacher.exercise_generator import ExerciseVariant
    from piano_teacher.lesson_stage_semantics import teaching_sequence

    baseline = LearningPlan(piece, exercise_strategy="coda-fukuda-midi").stages[-1]
    original = baseline.variant
    first = original.notes[0]
    pitched = ExerciseStage(
        ExerciseVariant("custom-interval-drill",
            replace(original.phrase, notes=(replace(first, pitch=first.pitch + 1),
                *original.notes[1:])), original.source_indices),
        origin="external-pitch-generator", technique="pitch-change",
        display_name="Interval drill")
    dynamics = ExerciseStage(
        ExerciseVariant("custom-accent-drill",
            replace(original.phrase, notes=(replace(first, velocity=max(1, first.velocity-10)),
                *original.notes[1:])), original.source_indices),
        origin="external-dynamics-generator", technique="dynamic-change",
        display_name="Accent drill")
    changed_pitch = difference(pitched, baseline)
    changed_dynamic = difference(dynamics, baseline)
    assert changed_pitch.pitch_changed == 1 and changed_pitch.meaningful
    assert changed_dynamic.velocity_changed == 1 and changed_dynamic.meaningful
    assert fingerprint(pitched) != fingerprint(baseline)
    assert fingerprint(dynamics) != fingerprint(baseline)
    assert teaching_sequence((pitched, dynamics, baseline)) == (
        pitched, dynamics, baseline)
    assert describe(pitched, baseline)["label"] == "Interval drill"
    assert describe(dynamics, baseline)["change"] == "1 changed dynamics"


def test_default_slowdown_stage_uses_native_score_listen_and_grader_on_original_piece(tmp_path):
    piece=load_midi(THREE_FOUR)
    plan=LearningPlan(piece,exercise_strategy="coda-fukuda-midi")
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

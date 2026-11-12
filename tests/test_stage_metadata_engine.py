"""Stage metadata drives the live engine: tempo maps, rhythm and grading.

Stages come from a test generator (tests/stage_fixtures.py), not from a
selectable rhythm or tempo strategy; the engine reads only the metadata.
"""
from dataclasses import dataclass

import pytest

from piano_teacher.application.practice_assessment import (
    FixedTimingPolicy, MappedTimingPolicy, PracticeAssessmentPolicies,
)
from piano_teacher.application.score_artifacts import ScoreSelection
from piano_teacher.assessment_service import AssessmentService
from piano_teacher.exercise_contracts import (
    OriginalTiming, TempoMap, TempoSegment, assess_timed,
)
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote
from piano_teacher.server import PracticeEngine
from piano_teacher.timed_assessment import assess_timed_window
from stage_fixtures import StagedTestGenerator, select_level


def source():
    notes = tuple(
        Note(float(i), float(i)+1.0, 65+i, 0, 0, "right",
             f"source-{i}", "voice-1")
        for i in range(4))
    return Piece("Stage metadata", 80, notes,
                 (Phrase(1, 1, 1, 0, 4, notes),),
                 bar_boundaries=(0.0, 4.0))


@dataclass(frozen=True)
class CustomTempo:
    """Unregistered policy: no hardcoded ID or stage-level check."""
    name: str = "my-unregistered-shape"

    def effective_bpm(self, bpm):
        return bpm*.5

    def ladder_bpm(self, effective_bpm):
        return effective_bpm/.5

    def generate(self, plan, target_bpm):
        return TempoMap(self.name, (
            TempoSegment(0, plan.duration_beats*.5, target_bpm*.5),
            TempoSegment(plan.duration_beats*.5, plan.duration_beats,
                         target_bpm),
        ))


def test_unregistered_tempo_policy_operates_in_live_engine_without_engine_change(tmp_path):
    piece = source()
    plan = LearningPlan(piece, lesson_generator=StagedTestGenerator(tempo=CustomTempo()))
    select_level(plan, "my-unregistered-shape")
    plan.bpm = 60
    assert plan.active_stage.shaped_tempo
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = plan
        engine.mode = "practice"
        assert engine._active_tempo_map().name == "my-unregistered-shape"
        assert engine._elapsed_seconds(2) == pytest.approx(4.0)
        assert engine._elapsed_beat(4.0) == pytest.approx(2.0)
        assert not engine._score_selection().transformed_rhythm
    finally:
        engine.db.close()


def test_score_selection_marks_transformed_rhythm_without_parsing_stage_key(tmp_path):
    plan = LearningPlan(source(), lesson_generator=StagedTestGenerator(long_first=False))
    select_level(plan, "dotted-short-long")
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = plan
        engine.mode = "practice"
        selection = engine._score_selection()
        assert selection.transformed_rhythm
        assert selection.stage_key == plan.identity
        # Metadata, rather than the opaque progress key, selects engraving.
        changed = ScoreSelection(
            selection.piece, selection.phrase, selection.hand,
            "arbitrary-key-without-timing-name", selection.revision,
            selection.fingerprint, transformed_rhythm=True)
        assert changed.transformed_rhythm
        assert changed.identity != ScoreSelection(
            changed.piece, changed.phrase, changed.hand, changed.stage_key,
            changed.revision, changed.fingerprint,
            transformed_rhythm=False).identity
        select_level(plan, "original")
        assert not engine._score_selection().transformed_rhythm
    finally:
        engine.db.close()


def test_historical_and_live_grading_share_per_note_clock():
    piece = source()
    plan = LearningPlan(piece, lesson_generator=StagedTestGenerator())
    select_level(plan, "two-phase-tempo")
    original = plan.active_variant
    timing = OriginalTiming().transform(original)
    tempo = plan.active_stage.tempo_map(60)
    played = [PlayedNote(
        note.pitch, tempo.seconds_at(note.start),
        tempo.seconds_at(note.end))
        for note in original.notes]
    historical = assess_timed(timing, "right", 60, played, tempo_map=tempo)
    runtime = assess_timed_window(original.phrase, "right", tempo, played)
    assert historical.assessment.clean
    assert runtime.clean
    assert [entry.status for entry in historical.assessment.notes] == [
        entry.status for entry in runtime.notes]


def test_assessment_policies_are_injectable_without_session_mutation():
    assessment = AssessmentService()
    suite = PracticeAssessmentPolicies(
        FixedTimingPolicy(assessment), MappedTimingPolicy())
    assert suite.select(None) is suite.fixed
    map_ = TempoMap("unknown", (TempoSegment(0, 4, 67),))
    assert suite.select(map_) is suite.mapped
    assert suite.select(map_).grade(
        source().phrases[0], hand="right", bpm=67,
        played=[PlayedNote(n.pitch, map_.seconds_at(n.start),
                           map_.seconds_at(n.end)) for n in source().notes],
        from_beat=0, end_beat=4, tempo=map_).clean


def test_policy_settings_persist_without_resetting_current_practice(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.fingerprint = "policy-fixture"
        engine.plan = LearningPlan(source())
        original_plan = engine.plan
        original_key = engine.plan.identity
        original_bpm = engine.plan.bpm
        returned = engine.set_preferences(
            diagnosis_strategy="accuracy-only",
            learner_strategy="repeat-only")
        assert returned["diagnosis_strategy"] == "accuracy-only"
        assert returned["learner_strategy"] == "repeat-only"
        assert engine.practice_policy.diagnosis.name == "accuracy-only"
        assert engine.practice_policy.learner.name == "repeat-only"
        assert engine.plan is original_plan
        assert engine.plan.identity == original_key
        assert engine.plan.bpm == original_bpm
        assert engine.mode == "practice"
    finally:
        engine.db.close()
    reloaded = PracticeEngine(tmp_path, enable_midi=False)
    try:
        assert reloaded.practice_policy.diagnosis.name == "accuracy-only"
        assert reloaded.practice_policy.learner.name == "repeat-only"
        with pytest.raises(ValueError):
            reloaded.set_preferences(diagnosis_strategy="nonexistent")
    finally:
        reloaded.db.close()

"""Step 4 contracts: explanatory difficulty, source-safe drills and remediation."""
from dataclasses import dataclass, replace

import pytest

from piano_teacher.difficulty import DifficultyEstimate, HeuristicDifficulty
from piano_teacher.exercise_contracts import (
    ChordBlockTiming, OriginalTiming, resolve_timing_strategy)
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.exercise_strategies import (
    CodaPartStrategy, ExerciseContext, FeatureGatedStrategy, resolve_strategy)
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import Assessment, NoteAssessment
from piano_teacher.remediation import RemediationPlanner
from piano_teacher.diagnosis_policies import PracticeRecommendation
from piano_teacher.server import PracticeEngine


def source(count=8, *, two_bars=True):
    notes = tuple(Note(float(i), float(i)+.75, 60+i, 0, 0,
                       "right", f"src-{i}", "v1") for i in range(count))
    end = 8 if two_bars else 4
    phrase = Phrase(1, 1, 2 if two_bars else 1, 0, end, notes)
    return Piece("Step 4", 80, notes, (phrase,),
                 bar_boundaries=(0, 4, 8) if two_bars else (0, 4))


def test_features_are_explainable_and_estimator_injectable():
    p = source()
    report = HeuristicDifficulty().estimate(p.notes, 8)
    assert report.features.attack_count == 8
    assert report.features.max_melodic_leap == 1
    assert report.features.peak_chord_size == 1
    assert report.features.as_dict()["attacks_per_beat"] == 1.0
    assert report.level == "baseline"

    class CustomEstimator:
        name = "custom"
        def estimate(self, notes, beats):
            return DifficultyEstimate("challenging", "rhythm",
                                      ("injected",), report.features)

    generated = FeatureGatedStrategy(CustomEstimator()).generate(
        ExerciseContext(p.phrases[0], "right"),
        lambda: (ExerciseVariant("original", p.phrases[0], tuple(range(8))),))
    assert generated[0].level.startswith("coda")


def test_coda_multiple_stages_are_nested_and_preserve_original():
    p = source().phrases[0]
    stages = resolve_strategy("coda-part").generate(
        ExerciseContext(p, "right", max_attacks=8),
        lambda: ())
    assert [v.level for v in stages] == ["coda-part-a", "coda-part-b", "original"]
    assert len(stages[0].notes) == 4 and len(stages[1].notes) == 6
    assert stages[-1].notes == p.notes
    assert set(stages[0].source_indices) < set(stages[1].source_indices)


def test_chordification_retains_source_id_and_rejects_repeated_unisons():
    p = source().phrases[0]
    p = replace(p, notes=tuple(replace(note, end=note.start+1.0)
                               for note in p.notes))
    source_variant = ExerciseVariant("original", p, tuple(range(len(p.notes))))
    timing = resolve_timing_strategy("coda-chord-blocks").transform(source_variant)
    assert isinstance(resolve_timing_strategy("coda-chord-blocks"), ChordBlockTiming)
    assert timing.events[1].exercise_start == timing.events[0].exercise_start
    assert timing.events[1].exercise_end == timing.events[0].exercise_end
    assert timing.events[3].exercise_start == timing.events[2].exercise_start
    assert timing.exercise_phrase.notes[1].source_id == p.notes[1].source_id
    repeated = tuple(Note(float(i), float(i)+1, 60, 0, 0,
                          "right", f"repeat-{i}", "v1") for i in range(2))
    variant = ExerciseVariant("original", Phrase(1, 1, 1, 0, 4, repeated), (0, 1))
    assert ChordBlockTiming().transform(variant).events == OriginalTiming().transform(variant).events


def test_remediation_selects_wrong_chord_and_does_not_change_source_stage():
    p = source().phrases[0]
    notes = p.notes
    variant = ExerciseVariant("original", p, tuple(range(len(notes))))
    result = Assessment(tuple(NoteAssessment(n, "wrong" if i in (3, 4)
                                            else "correct") for i, n in enumerate(notes)), 0)
    request = PracticeRecommendation("pitch", "note-isolation", "two repeated attempts")
    assignment = RemediationPlanner().plan(
        request, result, variant, stage_key="source-lesson",
        boundaries=(0, 4, 8))
    assert assignment is not None and assignment.guided
    assert assignment.start_beat == 0 and assignment.end_beat == 8
    assert set(assignment.variant.source_indices) == {3, 4}
    assert [n.source_id for n in assignment.variant.notes] == ["src-3", "src-4"]
    assert variant.notes == notes
    assert RemediationPlanner().plan(
        PracticeRecommendation("accuracy", "repeat", "baseline"),
        result, variant, stage_key="source-lesson",
        boundaries=(0, 4, 8)) is None


def test_remediation_never_creates_unscored_mastery_and_repeat_only_stays_manual(tmp_path):
    p = source(4, two_bars=False)
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(p)
        engine.fingerprint = "step4-fixture"
        stage = engine.plan.identity
        errors = Assessment(tuple(
            NoteAssessment(n, "wrong" if i == 1 else "correct")
            for i, n in enumerate(engine.plan.active_variant.notes)), 0)
        assert errors.notes and any(n.status == "wrong" for n in errors.notes)
        for attempt in range(2):
            engine.mode = "practice"
            engine.auto = True
            engine.pending_result = errors
            engine._commit_pending()
        assert engine._remediation_pending is not None
        assert engine._remediation_pending.action == "note-isolation"
        assert stage == engine.plan.identity
        assert stage not in engine.plan.mastered
        assignment = engine._remediation_pending
        engine._start_remedial_assignment(assignment)
        assert engine.mode == "learn"
        assert engine._remediation_active is not None
        assert len(engine._remediation_active.variant.notes) == 1
        assert stage not in engine.plan.mastered
    finally:
        engine.db.close()

    baseline = PracticeEngine(tmp_path/"baseline", enable_midi=False)
    try:
        baseline.set_preferences(learner_strategy="repeat-only")
        baseline.plan = LearningPlan(p)
        baseline.fingerprint = "baseline"
        for attempt in range(2):
            baseline.mode = "practice"
            baseline.auto = True
            baseline.pending_result = errors
            baseline._commit_pending()
        assert baseline._remediation_pending is None
    finally:
        baseline.db.close()


def test_fukuda_keeps_annotated_inner_chord_pitch():
    notes = (
        Note(0, 1, 60, 0, 0, "right", "root", "v1"),
        Note(0, 1, 64, 0, 0, "right", "middle", "v1"),
        Note(0, 1, 67, 0, 0, "right", "top", "v1"),
        Note(1, 2, 72, 0, 0, "right", "last", "v1"),
    )
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    groups = (("slur", (frozenset({1}), frozenset({3}))),)
    variants = resolve_strategy("fukuda").generate(
        ExerciseContext(phrase, "right", groups), lambda: ())
    assert all(1 in variant.source_indices for variant in variants)
    assert variants[-1].notes == notes


def test_coda_chord_blocks_are_accessible_through_pipeline_and_score_model(tmp_path):
    from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
    from piano_teacher.preprocessing_cache import PreprocessingCache
    notes = tuple(Note(float(i), float(i)+1, pitch, 0, 0, "right",
                       f"chord-src-{i}", "v1")
                  for i, pitch in enumerate((60, 64, 67, 71)))
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    piece = Piece("Chord blocks", 80, notes, (phrase,),
                  bar_boundaries=(0, 4))
    plan = LearningPlan(piece, timing_strategy="coda-chord-blocks")
    index = next(i for i, stage in enumerate(plan.stages)
                 if stage.transformed_rhythm)
    plan.variant_index = index
    assert plan.active_variant.level == "coda-chord-blocks"
    assert plan.variants[-1].level == "original"
    assert plan.active_variant.notes[1].start == 0
    assert plan.active_variant.notes[3].start == 2
    artifacts = ScoreArtifacts(PreprocessingCache(tmp_path/"preprocessed"))
    selection = ScoreSelection(piece, plan.active_phrase, "right", plan.identity,
                               1, "test-source", transformed_rhythm=True)
    model = artifacts.source_model(selection)
    actual = {n["id"]: n for n in model["notes"]}
    assert set(actual) == {n.source_id for n in notes}
    assert actual["chord-src-1"]["onset_beats"] == 0
    assert actual["chord-src-3"]["onset_beats"] == 2
    assert tuple(n.start for n in piece.notes) == (0, 1, 2, 3)


@pytest.mark.parametrize("status,action", [
    ("early", "timing-practice"),
    ("short", "sustain-practice"),
])
def test_repeated_timing_or_duration_errors_route_to_partial_nonmastery_retry(
        tmp_path, status, action):
    piece = source(4, two_bars=False)
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(piece, exercise_strategy="legacy")
        engine.fingerprint = "timing-errors"
        identity = engine.plan.identity
        result = Assessment(tuple(NoteAssessment(n, status if i < 2 else "correct")
                                  for i, n in enumerate(engine.plan.active_variant.notes)), 0)
        for attempt in range(2):
            engine.mode = "practice"
            engine.auto = True
            engine.pending_result = result
            engine._commit_pending()
        assignment = engine._remediation_pending
        assert assignment is not None and assignment.action == action
        assert not assignment.guided
        engine._start_remedial_assignment(assignment)
        assert engine.mode == "practice"
        assert engine.review_end_beat == 4
        assert engine.retry_range["first_bar"] == 1
        assert identity not in engine.plan.mastered
        assert engine.auto is False
        assert "cannot award mastery" in engine.next_action
    finally:
        engine.db.close()


def test_manual_attempt_never_automatically_routes_a_remedial_session(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(source(4, two_bars=False))
        engine.fingerprint = "manual"
        result = Assessment(tuple(NoteAssessment(n, "wrong")
                                  for n in engine.plan.active_variant.notes), 0)
        for attempt in range(2):
            engine.mode = "practice"
            engine.auto = False
            engine.pending_result = result
            engine._commit_pending()
        assert engine._remediation_pending is None
    finally:
        engine.db.close()

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

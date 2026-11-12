"""Evidence-driven remediation routing on the source course.

Moved from the retired step-4 strategy tests: the remediation planner and
the repeat-only learner policy are strategy-independent and still current.
"""
import pytest

from piano_teacher.diagnosis_policies import PracticeRecommendation
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import Assessment, NoteAssessment
from piano_teacher.remediation import RemediationPlanner
from piano_teacher.server import PracticeEngine


def source(count=8, *, two_bars=True):
    notes = tuple(Note(float(i), float(i)+.75, 60+i, 0, 0,
                       "right", f"src-{i}", "v1") for i in range(count))
    end = 8 if two_bars else 4
    phrase = Phrase(1, 1, 2 if two_bars else 1, 0, end, notes)
    return Piece("Step 4", 80, notes, (phrase,),
                 bar_boundaries=(0, 4, 8) if two_bars else (0, 4))


def settle_exposure(engine, result, *, automatic=True):
    """Give diagnostics a completed take from the one production ledger."""
    engine.midi.port = object()
    engine.start()
    engine.auto = automatic
    engine.measurement.seal(engine.recorder.presses, state="completed",
                            reason="full_passage", result=result,
                            eligible=engine.plan.bpm >= engine.plan.target_bpm)
    engine.pending_result = result
    engine._pending_assessed_bpm = engine.plan.bpm
    engine._commit_pending()


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
            settle_exposure(engine, errors)
        assert len(engine.progress.ledger.recent(engine.fingerprint, stage).recent) == 2
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
            settle_exposure(baseline, errors)
        assert len(baseline.progress.ledger.recent(baseline.fingerprint, baseline.plan.identity).recent) == 2
        assert baseline._remediation_pending is None
    finally:
        baseline.db.close()


@pytest.mark.parametrize("status,action", [
    ("early", "timing-practice"),
    ("short", "sustain-practice"),
])
def test_repeated_timing_or_duration_errors_route_to_partial_nonmastery_retry(
        tmp_path, status, action):
    piece = source(4, two_bars=False)
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(piece, exercise_strategy="source-progression")
        engine.fingerprint = "timing-errors"
        identity = engine.plan.identity
        result = Assessment(tuple(NoteAssessment(n, status if i < 2 else "correct")
                                  for i, n in enumerate(engine.plan.active_variant.notes)), 0)
        for attempt in range(2):
            settle_exposure(engine, result)
        assert len(engine.progress.ledger.recent(engine.fingerprint, identity).recent) == 2
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
            settle_exposure(engine, result, automatic=False)
        assert len(engine.progress.ledger.recent(engine.fingerprint, engine.plan.identity).recent) == 2
        assert engine._remediation_pending is None
    finally:
        engine.db.close()

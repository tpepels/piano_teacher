"""Characterize state transitions for the four end-of-take routes."""
from types import SimpleNamespace as Obj
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine
from piano_teacher.practice import Assessment, NoteAssessment


def _engine(tmp_path):
    note = Note(0, 1, 60, 0, 0, "right")
    phrase = Phrase(1, 1, 2, 0, 8, (note,))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(Piece(
        "Completion", 100, (note,), (phrase,), bar_boundaries=(0, 4, 8)))
    return engine


def test_section_review_never_advances_mastery(tmp_path):
    engine = _engine(tmp_path)
    try:
        result = Obj(summary="Review feedback")
        engine.auto = True
        engine.review_end_beat = 4.0
        engine.pending_rewind = 2.0
        engine.open_from_beat = 2.0
        engine.retry_range = {"first_bar":1}
        identity = engine.plan.identity
        engine._finish_section_review(result)
        assert not engine.auto
        assert engine.review_session_complete
        assert engine.review_end_beat is None
        assert engine.pending_rewind is None and engine.retry_range is None
        assert engine.open_from_beat == 0
        assert engine.pending_result is None
        assert engine.plan.identity == identity
        assert engine.feedback == "Section review finished · Review feedback"
    finally:
        engine.db.close()


def test_clean_performance_review_leaves_course_progress_unmodified(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.performance_summary = {"weakest_bars":[]}
        engine.auto = True
        before = (engine.plan.identity, engine.plan.bpm, engine.plan.streak)
        result = Obj(clean=True)
        engine._finish_performance_review(engine.plan.active_phrase, result)
        assert (engine.plan.identity, engine.plan.bpm, engine.plan.streak) == before
        assert engine.next_action.startswith("Clean performance")
        assert not engine.auto and engine.pending_result is None
    finally:
        engine.db.close()


def test_partial_recovery_schedules_whole_passage_without_mastery(tmp_path):
    engine = _engine(tmp_path)
    try:
        calls = []
        engine._schedule_preparation = lambda *args, **kwargs: calls.append((args, kwargs))
        engine.play_from_beat = 2.0
        engine.run_at = 90.0
        engine.visual_offset_beats = 8.0
        engine.retry_range = {"first_bar":1}
        identity = engine.plan.identity
        engine._finish_partial_recovery(Obj(summary="Partial pass"), 100)
        assert len(calls) == 1 and calls[0][0] == (0.0,)
        assert calls[0][1]["now"] == 100
        assert engine.pending_result is None
        assert engine.retry_range is None and engine.plan.identity == identity
        assert engine.next_action == "Next: play the whole passage from its beginning to earn mastery."
    finally:
        engine.db.close()


def test_full_passage_result_waits_for_feedback_commit(tmp_path):
    engine = _engine(tmp_path)
    try:
        result = Obj(clean=True)
        engine.auto = False
        engine.plan.streak = 1
        engine._finish_full_passage(result, 8, 8, 100)
        assert engine.pending_result is result
        assert engine.plan.streak == 1 and not engine.plan.mastered
        assert engine.next_at == 0
    finally:
        engine.db.close()

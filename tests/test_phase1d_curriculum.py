"""Full lesson path, uniquely mastered stages and explicit-cancel semantics."""
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def piece():
    notes = (
        Note(0, .8, 60, 0, 0, "right"), Note(0, .8, 64, 0, 0, "right"),
        Note(0, .8, 67, 0, 0, "right"), Note(0, .8, 48, 1, 0, "left"),
        Note(0, .8, 52, 1, 0, "left"), Note(1, 1.8, 69, 0, 0, "right"),
        Note(8, 8.8, 62, 0, 0, "right"), Note(8, 8.8, 65, 0, 0, "right"),
        Note(8, 8.8, 69, 0, 0, "right"), Note(8, 8.8, 50, 1, 0, "left"),
    )
    return Piece("Lessons", 100, notes, (
        Phrase(1, 1, 2, 0, 8, tuple(n for n in notes if n.start < 8)),
        Phrase(2, 3, 4, 8, 16, tuple(n for n in notes if n.start >= 8)),
    ))


def test_curriculum_lists_every_hand_and_generated_level():
    p = LearningPlan(piece())
    steps = p.lesson_steps
    assert len(steps) > len(p.exercises)
    assert steps[0].hand == "right"
    assert steps[0].level == "skeleton"
    assert any(s.hand == "left" for s in steps)
    assert any(s.hand == "both" for s in steps)
    assert any(s.kind == "connect" for s in steps)
    assert any(s.kind == "perform" for s in steps)
    assert len({s.key for s in steps}) == len(steps)
    assert p.lesson_step_number == 1
    assert p.lesson_steps_mastered == 0


def test_three_clean_plays_unlock_exactly_one_lesson_step():
    p = LearningPlan(piece())
    p.set_bpm(100)
    first = p.identity
    count = len(p.active_phrase.notes)
    for _ in range(2):
        assert "Clean pass" in p.apply_result(correct=count, total=count)
    assert p.lesson_step_number == 1
    assert p.lesson_steps_mastered == 0
    p.apply_result(correct=count, total=count)
    assert p.identity != first
    assert p.lesson_step_number == 2
    assert p.lesson_steps_mastered == 1
    assert first in p.mastered


def test_curriculum_api_matches_active_stage(tmp_path):
    e=PracticeEngine(tmp_path,enable_midi=False)
    e.plan=LearningPlan(piece())
    try:
        overview=e.lesson_overview()
        assert overview["current_step"] == e.state()["lesson_step"] == 1
        assert overview["total_steps"] == e.state()["lesson_steps"]
        assert overview["steps"][0]["key"] == e.plan.identity
        assert overview["steps"][0]["required_notes"] == e.state()["required_notes"]
    finally:
        e.db.close()


def test_manual_stop_during_feedback_discards_uncommitted_mastery(tmp_path):
    e=PracticeEngine(tmp_path,enable_midi=False)
    p=LearningPlan(piece())
    p.set_bpm(100)
    e.plan=p
    e.fingerprint="cancelled-performance"
    try:
        n=len(p.active_phrase.notes)
        e.pending_result=type("Result",(),{"correct":n,"extra_notes":0,"notes":[1]*n})()
        e.auto=True
        e.next_at=99999999
        e.control("stop")
        assert p.streak==0
        assert p.mastered=={}
        assert e.pending_result is None
        assert not e.running
    finally:
        e.db.close()


def test_manual_navigation_discards_pending_take(tmp_path):
    e=PracticeEngine(tmp_path,enable_midi=False)
    e.plan=LearningPlan(piece())
    e.fingerprint="cancelled-navigation"
    try:
        e.pending_result=type("Result",(),{"correct":1,"extra_notes":0,"notes":[1]})()
        e.control("next")
        assert e.plan.index==1
        assert not e.plan.mastered
        assert e.plan.streak==0
    finally:
        e.db.close()

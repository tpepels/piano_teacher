"""Guided selection and persistence do not require PracticeEngine."""
from types import SimpleNamespace

from piano_teacher.application import learner_progress as module
from piano_teacher.application.learner_progress import LearnerProgress


class Store:
    def __init__(self):
        self.completed = []
    def complete_unit(self, fingerprint, key, unit, *, assisted):
        self.completed.append((fingerprint, key, unit, assisted))


def test_next_course_unit_uses_first_unfinished_before_explicit_restart(monkeypatch):
    first = {"start_beat": 0}
    second = {"start_beat": 4}
    calls = []
    def next_unit(variant, boundaries, saved):
        calls.append((variant, boundaries, saved))
        return second if saved["unfinished"] else None
    monkeypatch.setattr(module, "next_guided_unit", next_unit)
    monkeypatch.setattr(module, "guided_units", lambda variant, bounds: (first, second))
    variant = SimpleNamespace()
    boundaries = (0, 4, 8)
    assert LearnerProgress.next_course_unit(
        variant, boundaries, {"unfinished": True}, explicit_learn=False) is second
    assert LearnerProgress.next_course_unit(
        variant, boundaries, {"unfinished": False}, explicit_learn=False) is None
    assert LearnerProgress.next_course_unit(
        variant, boundaries, {"unfinished": False}, explicit_learn=True) is first
    assert len(calls) == 3


def test_completed_guided_preparation_is_persisted_only_when_bound_to_a_piece():
    store = Store()
    progress = LearnerProgress(store)
    unit = {"start_beat": 4, "end_beat": 8}
    progress.record_guided_preparation(
        fingerprint="score", stage_key="hand", unit=unit, assisted_count=2)
    progress.record_guided_preparation(
        fingerprint="", stage_key="hand", unit=unit, assisted_count=0)
    progress.record_guided_preparation(
        fingerprint="score", stage_key="hand", unit=None, assisted_count=0)
    assert store.completed == [("score", "hand", unit, True)]
    progress.record_guided_preparation(
        fingerprint="score", stage_key="hand", unit=unit, assisted_count=0)
    assert store.completed[-1] == ("score", "hand", unit, False)

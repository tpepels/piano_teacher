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


def test_skip_validation_precedes_session_stop():
    import pytest
    plan = SimpleNamespace(
        lesson_step_number=1,
        lesson_steps=[SimpleNamespace(key="first"), SimpleNamespace(key="second")])
    assert LearnerProgress.next_skippable_step(plan,"need to advance").key == "second"
    for reason in ("", "  ", None, 5):
        with pytest.raises(ValueError, match="Choose an available next step"):
            LearnerProgress.next_skippable_step(plan,reason)
    plan.lesson_step_number=2
    with pytest.raises(ValueError, match="Choose an available next step"):
        LearnerProgress.next_skippable_step(plan,"skip")


def test_skip_persistence_uses_explicit_fingerprint():
    class SkipStore(Store):
        def __init__(self):
            super().__init__()
            self.skipped = []
        def mark_skipped(self, fingerprint, stage, **kwargs):
            self.skipped.append((fingerprint,stage,kwargs))
    store=SkipStore()
    owner=LearnerProgress(store)
    owner.mark_skipped(fingerprint="",stage_key="r",reason="short")
    owner.mark_skipped(fingerprint="piece",stage_key="r",reason="short")
    assert store.skipped == [("piece","r",{"reason":"short"})]


def test_source_trouble_validation_rejects_invalid_boundaries():
    import pytest
    owner=LearnerProgress(Store())
    for beat in (True, None, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="Choose a saved trouble spot"):
            owner.choose_trouble_spot(None, fingerprint="piece",
                                     stage_key="right", start_beat=beat)


def test_rolling_trouble_records_only_source_attacks_inside_selected_idea():
    class TrackingStore(Store):
        def __init__(self):
            super().__init__()
            self.events = []
        def record_trouble(self, fingerprint, stage, unit, *, errors, pitches):
            self.events.append(("trouble", fingerprint, stage, unit, errors, pitches))
        def save_resume(self, fingerprint, stage, unit):
            self.events.append(("resume", fingerprint, stage, unit))
        def resolve_trouble(self, fingerprint, stage):
            self.events.append(("resolve", fingerprint, stage))
    store = TrackingStore()
    owner = LearnerProgress(store)
    unit = {"start_beat":4.0,"end_beat":8.0}
    def note(beat, pitch, status):
        return SimpleNamespace(
            note=SimpleNamespace(start=100.0+beat, pitch=pitch), status=status)
    notes = [
        note(2.0,60,"missed"), note(4.0,65,"wrong"),
        note(5.0,67,"missed"), note(6.0,69,"correct"),
        note(8.0,72,"wrong"), note(7.5,65,"wrong")]
    owner.record_rolling_trouble(
        fingerprint="piece", stage_key="right", unit=unit,
        assessed_notes=notes, phrase_start=100.0)
    assert store.events == [
        ("trouble","piece","right",unit,3,[65,67]),
        ("resume","piece","right",unit)]
    owner.resolve_trouble(fingerprint="piece",stage_key="right")
    assert store.events[-1] == ("resolve","piece","right")
    owner.save_resume(fingerprint="",stage_key="right",unit=unit)
    owner.resolve_trouble(fingerprint="",stage_key="right")
    assert len(store.events)==3

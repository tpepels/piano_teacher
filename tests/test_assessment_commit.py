"""LearningPlan commit and adaptive evidence have explicit boundaries."""
from types import SimpleNamespace

from piano_teacher.application import assessment_commit as module


class Plan:
    def __init__(self, *, outcome="same"):
        self.identity = "right-hand"
        self.bpm = 50
        self.exercise = SimpleNamespace(kind="learn")
        self.active_variant = object()
        self.piece = SimpleNamespace(bar_boundaries=(0, 4, 8))
        self.outcome = outcome
        self.calls = []

    def apply_result(self, *, correct, total, extras, accepted):
        self.calls.append((correct, total, extras, accepted))
        if self.outcome == "advance":
            self.identity = "together"
        elif self.outcome == "speedup":
            self.bpm = 55
        return "Continue"


def take(*, clean=False):
    return SimpleNamespace(
        clean=clean, correct=1, extra_notes=0,
        notes=[SimpleNamespace(status="wrong")])


def test_evidence_uses_previous_stage_before_plan_advancement(monkeypatch):
    plan = Plan(outcome="advance")
    seen = []
    def observe(**kwargs):
        seen.append((kwargs["stage_key"],kwargs["bpm"],plan.identity))
        return None
    monkeypatch.setattr(module, "observe_assessed_take", observe)
    result = module.commit_assessed_result(
        plan=plan, result=take(clean=True), fingerprint="piece",
        automatic=True, mode="practice", warmup=False,
        observe=lambda *_: None, plan_remediation=lambda *a, **kw: None)
    assert seen == [("right-hand", 50, "right-hand")]
    assert result.previous_stage == "right-hand"
    assert result.stage_changed
    assert not result.accelerated
    assert plan.calls == [(1, 1, 0, True)]


def test_tempo_progress_is_not_mistaken_for_new_score_revision(monkeypatch):
    monkeypatch.setattr(module, "observe_assessed_take", lambda **kw: None)
    plan = Plan(outcome="speedup")
    outcome = module.commit_assessed_result(
        plan=plan, result=take(clean=True), fingerprint="piece",
        automatic=True, mode="practice", warmup=False,
        observe=lambda *_: None, plan_remediation=lambda *a, **kw: None)
    assert outcome.accelerated and not outcome.stage_changed
    assert outcome.previous_bpm == 50
    assert plan.bpm == 55


def test_remediation_requires_unaccepted_automatic_practice(monkeypatch):
    calls = []
    monkeypatch.setattr(module, "observe_assessed_take",
                        lambda **kw: "needs_pitch_work")
    def remediate(*args, **kwargs):
        calls.append((args,kwargs))
        return {"remediate":True}
    plan = Plan()
    outcome = module.commit_assessed_result(
        plan=plan, result=take(clean=False), fingerprint="piece",
        automatic=True, mode="practice", warmup=False,
        observe=lambda *_: None, plan_remediation=remediate)
    assert outcome.remediation == {"remediate":True}
    assert calls[0][1]["stage_key"] == "right-hand"
    assert calls[0][1]["boundaries"] == (0, 4, 8)
    assert plan.calls == [(1, 1, 0, False)]

    for auto, mode, warmup in [
        (False, "practice", False),
        (True, "perform", False),
        (True, "practice", True),
    ]:
        calls.clear()
        outcome = module.commit_assessed_result(
            plan=Plan(), result=take(clean=False), fingerprint="piece",
            automatic=auto, mode=mode, warmup=warmup,
            observe=lambda *_: None, plan_remediation=remediate)
        assert outcome.remediation is None
        assert calls == []

"""A2 committed successor effects fail closed on obsolete lesson identity."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from piano_teacher.application.settlement_continuation import SettlementContinuation
from piano_teacher.application.teaching_continuation import (
    ContinuationIdentity, StopSelectedContinuation,
    TeachingContinuation, FeedbackTransaction, SettledPublication,
)


def _subject():
    applied = []
    owner = object.__new__(SettlementContinuation)
    owner.lesson = SimpleNamespace(
        fingerprint="score-sha", revision=12,
        plan=SimpleNamespace(identity="next-hand"))
    owner.take = SimpleNamespace(
        pending=SimpleNamespace(
            decision=SimpleNamespace(decision_id="committed"),
            receipt=object(), phase="effects_applied"),
        publishing=lambda pending: nullcontext())
    owner._applied_continuation_effect = None
    owner.transport = SimpleNamespace(
        apply_continuation=lambda effect: (
            applied.append(effect),
            SimpleNamespace(feedback=None, start=None))[1])
    owner.notices = SimpleNamespace(feedback="", next_action="")
    effect = StopSelectedContinuation(
        ContinuationIdentity("committed", "score-sha", "next-hand", 12),
        "Lesson finished")
    return owner, effect, applied


def test_decided_continuation_is_applied_only_once():
    owner, effect, applied = _subject()
    owner.dispatch_effect(effect, 100.0)
    owner.dispatch_effect(effect, 101.0)
    assert applied == [effect]
    with pytest.raises(ValueError, match="Conflicting"):
        owner.dispatch_effect(
            StopSelectedContinuation(effect.identity, "different action"),
            102.0)


@pytest.mark.parametrize("mutation", [
    "missing_plan", "different_fingerprint", "different_stage",
    "different_revision", "different_decision", "unsettled",
    "wrong_phase", "removed_pending",
])
def test_obsolete_continuations_cannot_execute(mutation):
    owner, effect, applied = _subject()
    pending = owner.take.pending
    if mutation == "missing_plan":
        owner.lesson.plan = None
    elif mutation == "different_fingerprint":
        owner.lesson.fingerprint = "another-score"
    elif mutation == "different_stage":
        owner.lesson.plan.identity = "another-hand"
    elif mutation == "different_revision":
        owner.lesson.revision += 1
    elif mutation == "different_decision":
        pending.decision.decision_id = "other-decision"
    elif mutation == "unsettled":
        pending.receipt = None
    elif mutation == "wrong_phase":
        pending.phase = "settled"
    else:
        owner.take.pending = None
    with pytest.raises(ValueError, match="Stale or unsettled"):
        owner.dispatch_effect(effect, 100.0)
    assert not applied


def test_failed_feedback_keeps_selected_transaction_when_auto_stops():
    pending = SimpleNamespace()
    continuation = TeachingContinuation(
        transport=SimpleNamespace(continuation_pending=False))
    selected = FeedbackTransaction(pending, "selected", 7)
    continuation._feedback_transaction = selected
    assert continuation.begin_feedback(
        pending, now=110.0, automatic=False,
        revision=9, fingerprint="score-sha") is selected
    with pytest.raises(ValueError, match="Another selected decision"):
        continuation.begin_feedback(
            SimpleNamespace(), now=110.0, automatic=False,
            revision=9, fingerprint="score-sha")


def test_stopped_auto_worker_does_not_spin_on_failed_effect():
    owner, _effect, _applied = _subject()
    owner.transport.auto = False
    owner.score = SimpleNamespace(
        begin_feedback=lambda *args, **kwargs: pytest.fail(
            "Stopped playback must require explicit user Retry"))
    owner.advance_pending_feedback(now=120.0)

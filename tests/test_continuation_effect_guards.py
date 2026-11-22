"""A2 committed successor effects fail closed on obsolete lesson identity."""
from types import SimpleNamespace

import pytest

from piano_teacher.application.completion_continuations import CompletionContinuations
from piano_teacher.application.teaching_continuation import (
    ContinuationIdentity, StopSelectedContinuation,
)


def _subject():
    applied = []
    owner = object.__new__(CompletionContinuations)
    owner.source_identity = SimpleNamespace(
        fingerprint="score-sha", revision=12,
        plan=SimpleNamespace(identity="next-hand"))
    owner.attempt_settlement = SimpleNamespace(
        pending=SimpleNamespace(
            decision=SimpleNamespace(decision_id="committed"),
            receipt=object(), phase="effects_applied"))
    owner._applied_continuation_effect = None
    owner.playback_session = SimpleNamespace(
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
    pending = owner.attempt_settlement.pending
    if mutation == "missing_plan":
        owner.source_identity.plan = None
    elif mutation == "different_fingerprint":
        owner.source_identity.fingerprint = "another-score"
    elif mutation == "different_stage":
        owner.source_identity.plan.identity = "another-hand"
    elif mutation == "different_revision":
        owner.source_identity.revision += 1
    elif mutation == "different_decision":
        pending.decision.decision_id = "other-decision"
    elif mutation == "unsettled":
        pending.receipt = None
    elif mutation == "wrong_phase":
        pending.phase = "settled"
    else:
        owner.attempt_settlement.pending = None
    with pytest.raises(ValueError, match="Stale or unsettled"):
        owner.dispatch_effect(effect, 100.0)
    assert not applied

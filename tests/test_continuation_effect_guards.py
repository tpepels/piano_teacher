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
        future_score=None, transport=SimpleNamespace(next_at=0.0))
    selected = FeedbackTransaction(pending, "selected", 99.0, 7)
    continuation._feedback_transaction = selected
    assert continuation.begin_feedback(
        pending, now=110.0, automatic=False, force_early=False,
        revision=9, fingerprint="score-sha") is selected
    with pytest.raises(ValueError, match="Another selected decision"):
        continuation.begin_feedback(
            SimpleNamespace(), now=110.0, automatic=False,
            force_early=True, revision=9, fingerprint="score-sha")


def test_retry_of_committed_effect_retains_original_assessment_receipt():
    owner, effect, applied = _subject()
    pending = owner.take.pending
    pending.event = SimpleNamespace(kind="full_result")
    pending.receipt = SimpleNamespace(message="Original assessed result")
    pending.state = SimpleNamespace(route=SimpleNamespace(automatic=True))
    owner.take.finish_publication = (
        lambda: setattr(pending, "phase", "published"))
    vars(owner.take).update(
        clear_feedback=lambda: None,
        publication_finished=lambda: None,
        publication_failed=lambda: None)
    owner.score = SimpleNamespace(
        begin_feedback=lambda *args, **kwargs: SimpleNamespace(
            decision_id=effect.identity.decision_id, pending=pending),
        finish_feedback=lambda *args, **kwargs: SettledPublication(
            effect, None, "Original assessed result"))
    owner.commit_pending = lambda now, **kwargs: "Original assessed result"
    owner.transport.note_tempo = lambda **kwargs: None
    owner.lesson.plan.bpm = 72
    owner.transport_timing = SimpleNamespace(
        presentation_bpm=lambda: 72,
        next_count_in_beats=lambda: 4)
    owner.lesson.flow_active = False
    owner.clock = lambda: 110.0
    owner.transport.auto = False
    owner.transport.stop_automatic = lambda: None
    owner.transport.continue_course = lambda: setattr(
        owner.transport, "auto", True)

    assert owner.retry_failed_publication(now=110.0) == "Original assessed result"
    assert pending.phase == "published"
    assert applied == [effect]
    assert owner.transport.auto is True


def test_failed_committed_effect_does_not_publish_or_clear_feedback():
    owner, effect, _applied = _subject()
    pending = owner.take.pending
    pending.event = SimpleNamespace(kind="full_result")
    pending.receipt = SimpleNamespace(message="Original assessed result")
    pending.state = SimpleNamespace(route=SimpleNamespace(automatic=True))
    selected = SimpleNamespace(
        decision_id=effect.identity.decision_id, pending=pending)
    owner.score = SimpleNamespace(
        begin_feedback=lambda *args, **kwargs: selected,
        finish_feedback=lambda *args, **kwargs: SettledPublication(
            effect, None, "Original assessed result"))
    owner.commit_pending = lambda now, **kwargs: "Original assessed result"
    owner.transport.note_tempo = lambda **kwargs: None
    owner.lesson.plan.bpm = 72
    owner.transport_timing = SimpleNamespace(
        presentation_bpm=lambda: 72, next_count_in_beats=lambda: 4)
    owner.lesson.flow_active = False
    owner.transport.auto = True
    stopped = []
    owner.transport.stop_automatic = lambda: stopped.append(True)
    owner.transport.continue_course = lambda: None
    state = []
    vars(owner.take).update(
        clear_feedback=lambda: state.append("cleared"),
        publication_failed=lambda: state.append("failed"))
    owner.take.finish_publication = (
        lambda: state.append("published"))
    owner.dispatch_effect = lambda effect, now: (_ for _ in ()).throw(
        RuntimeError("physical continuation unavailable"))

    owner.advance_pending_feedback(110.0, force_early=True)
    assert state == ["failed"]
    assert stopped == [True]
    assert pending.phase == "effects_applied"
    assert "same saved result" in owner.notices.next_action


def test_stopped_auto_worker_does_not_spin_on_failed_effect():
    owner, _effect, _applied = _subject()
    owner.transport.auto = False
    owner.score = SimpleNamespace(
        begin_feedback=lambda *args, **kwargs: pytest.fail(
            "Stopped playback must require explicit user Retry"))
    owner.advance_pending_feedback(now=120.0, force_early=True)

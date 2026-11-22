"""A2 committed successor effects fail closed on obsolete lesson identity."""
from types import SimpleNamespace

import pytest

from piano_teacher.application.completion_continuations import CompletionContinuations
from piano_teacher.application.teaching_continuation import (
    ContinuationIdentity, StopSelectedContinuation,
    TeachingContinuation, FeedbackTransaction, SettledPublication,
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
    pending = owner.attempt_settlement.pending
    pending.event = SimpleNamespace(kind="full_result")
    pending.receipt = SimpleNamespace(message="Original assessed result")
    pending.state = SimpleNamespace(route=SimpleNamespace(automatic=True))
    owner.attempt_settlement.finish_publication = (
        lambda: setattr(pending, "phase", "published"))
    owner.attempt = SimpleNamespace(
        clear_feedback=lambda: None,
        publication_finished=lambda: None,
        publication_failed=lambda: None)
    owner.teaching_continuation = SimpleNamespace(
        begin_feedback=lambda *args, **kwargs: SimpleNamespace(
            decision_id=effect.identity.decision_id, pending=pending),
        finish_feedback=lambda *args, **kwargs: SettledPublication(
            effect, None, "Original assessed result"))
    owner.commit_pending = lambda **kwargs: "Original assessed result"
    owner.visual_transport = SimpleNamespace(
        note_tempo=lambda **kwargs: None)
    owner.source_identity.plan.bpm = 72
    owner.transport_timing = SimpleNamespace(
        presentation_bpm=lambda: 72,
        next_count_in_beats=lambda: 4)
    owner.lesson_execution = SimpleNamespace(flow_active=lambda: False)
    owner.clock = lambda: 110.0
    owner.playback_session.auto = False
    owner.playback_session.stop_automatic = lambda: None
    owner.playback_session.continue_course = lambda: setattr(
        owner.playback_session, "auto", True)

    assert owner.retry_failed_publication(now=110.0) == "Original assessed result"
    assert pending.phase == "published"
    assert applied == [effect]
    assert owner.playback_session.auto is True


def test_failed_committed_effect_does_not_publish_or_clear_feedback():
    owner, effect, _applied = _subject()
    pending = owner.attempt_settlement.pending
    pending.event = SimpleNamespace(kind="full_result")
    pending.receipt = SimpleNamespace(message="Original assessed result")
    pending.state = SimpleNamespace(route=SimpleNamespace(automatic=True))
    selected = SimpleNamespace(
        decision_id=effect.identity.decision_id, pending=pending)
    owner.teaching_continuation = SimpleNamespace(
        begin_feedback=lambda *args, **kwargs: selected,
        finish_feedback=lambda *args, **kwargs: SettledPublication(
            effect, None, "Original assessed result"))
    owner.commit_pending = lambda **kwargs: "Original assessed result"
    owner.visual_transport = SimpleNamespace(
        note_tempo=lambda **kwargs: None)
    owner.source_identity.plan.bpm = 72
    owner.transport_timing = SimpleNamespace(
        presentation_bpm=lambda: 72, next_count_in_beats=lambda: 4)
    owner.lesson_execution = SimpleNamespace(flow_active=lambda: False)
    owner.playback_session.auto = True
    stopped = []
    owner.playback_session.stop_automatic = lambda: stopped.append(True)
    owner.playback_session.continue_course = lambda: None
    state = []
    owner.attempt = SimpleNamespace(
        clear_feedback=lambda: state.append("cleared"),
        publication_failed=lambda: state.append("failed"))
    owner.attempt_settlement.finish_publication = (
        lambda: state.append("published"))
    owner.dispatch_effect = lambda effect, now: (_ for _ in ()).throw(
        RuntimeError("physical continuation unavailable"))

    owner.advance_pending_feedback(110.0, force_early=True)
    assert state == ["failed"]
    assert stopped == [True]
    assert pending.phase == "effects_applied"
    assert "same saved result" in owner.notices.next_action

"""Apply settled teaching continuation and exact feedback effects.

Accepts the sole AttemptSettlement receipt; applies typed, already-decided
successor effects. Does not choose an alternate stage, deadline or grade.
"""
from __future__ import annotations
from .teaching_continuation import (
    UnpreparedNextStage, FeedbackWaiting, FeedbackFault,
    SettledSourceFacts, EnterSelectedExposure, ApplySelectedResponse,
    EnterSelectedRemediation, ContinueSelectedScore,
)


class CompletionContinuations:
    def __init__(self, *, source_identity, notices, teaching_continuation,
                 attempt_settlement, playback_session, visual_transport,
                 attempt, flow_session, lesson_execution, transport_timing,
                 score_read, recovery_workflows, timed_playback, outcome_effects):
        self.source_identity, self.notices = source_identity, notices
        self.teaching_continuation, self.attempt_settlement = teaching_continuation, attempt_settlement
        self.playback_session, self.visual_transport = playback_session, visual_transport
        self.attempt, self.flow_session = attempt, flow_session
        self.lesson_execution, self.transport_timing = lesson_execution, transport_timing
        self.score_read, self.recovery_workflows = score_read, recovery_workflows
        self.timed_playback, self.outcome_effects = timed_playback, outcome_effects

    def advance_pending_feedback(self, now: float, *, force_early: bool = False):
        transaction = self.teaching_continuation.begin_feedback(
            self.attempt_settlement.pending,now=now,automatic=self.playback_session.auto,
            force_early=force_early,revision=self.source_identity.revision,fingerprint=self.source_identity.fingerprint)
        if isinstance(transaction,FeedbackWaiting):
            if transaction.message:
                self.notices.feedback = transaction.message
            return
        if isinstance(transaction,FeedbackFault):
            self.publish_feedback_fault(transaction,now)
            return
        try:
            self.outcome_effects.commit_pending(finish_publication=False)
            self.visual_transport.note_tempo(
            stage=self.source_identity.plan.identity,bpm=self.transport_timing.presentation_bpm(),now=now)
        except Exception as exc:
            self.publish_feedback_fault(self.teaching_continuation.settlement_failure(exc),now)
            if not isinstance(exc,UnpreparedNextStage):
                print("ASSESSMENT_SETTLEMENT_FAILED:",type(exc).__name__,str(exc),flush=True)
            return
        # The assessment is durable, but the selected successor has not
        # yet been applied. Retain its visible note feedback until the
        # exact source-bound continuation is successfully installed.
        publication = self.teaching_continuation.finish_feedback(transaction,SettledSourceFacts(
            fingerprint=self.source_identity.fingerprint,stage_key=self.source_identity.plan.identity,revision=self.source_identity.revision,
            now=now,bpm=self.source_identity.plan.bpm,presentation_bpm=self.transport_timing.presentation_bpm(),
            count_in_beats=self.transport_timing.next_count_in_beats(),automatic=self.playback_session.auto,
            flow_active=self.lesson_execution.flow_active()))
        if publication.flow_outcome is not None:
            self.flow_session.settle_decided(publication.flow_outcome,plan=self.source_identity.plan,
                message=publication.message,decision_id=transaction.decision_id)
        self.dispatch_effect(publication.effect,now)
        # Only a fully applied continuation may retire the old note marks
        # and acknowledge the once-only publication. If presentation fails,
        # the sealed assessment and its feedback remain visible for retry.
        self.attempt.clear_feedback()
        self.attempt_settlement.finish_publication()

    def publish_feedback_fault(self, fault: FeedbackFault, now: float) -> None:
        self.playback_session.apply_feedback_fault(fault,now=now)
        self.notices.feedback,self.notices.next_action = fault.feedback,fault.next_action

    def dispatch_effect(self, effect, now: float) -> None:
        """Apply typed source ports; every route/deadline was selected by its owner."""
        if isinstance(effect,EnterSelectedExposure):
            self.lesson_execution.enter_selected_exposure(effect.exposure)
        elif isinstance(effect,ApplySelectedResponse):
            self.recovery_workflows.apply_policy_response(effect.response,now=now,deadline=effect.deadline)
        elif isinstance(effect,EnterSelectedRemediation):
            self.recovery_workflows.start_remedial_assignment(effect.assignment,deadline=effect.deadline,
                exposure=effect.exposure)
        else:
            if isinstance(effect,ContinueSelectedScore):
                applied = self.playback_session.apply_continuation(effect,
                    measurement=self.transport_timing.collect_continuation_measurement(
                        effect.deadline,effect.exposure.from_beat),
                    source_stride_beats=self.score_read.source_model()["practice_timeline"]["stride_beats"])
            else:
                applied = self.playback_session.apply_continuation(effect)
            if applied.feedback is not None:
                self.notices.feedback = applied.feedback
            if applied.start is not None:
                self.timed_playback.continue_at(applied.start.deadline,from_beat=applied.start.from_beat)


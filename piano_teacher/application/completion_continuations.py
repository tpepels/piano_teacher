"""Apply settled teaching continuation and exact feedback effects.

Accepts the sole AttemptSettlement receipt; applies typed, already-decided
successor effects. Does not choose an alternate stage, deadline or grade.
"""
from __future__ import annotations
from .mistake_responses import resolve_mistake_policy
from .passage_outcome_presenter import performance_next_action
from .teaching_continuation import (
    UnpreparedNextStage, FeedbackWaiting, FeedbackFault,
    SettledSourceFacts, EnterSelectedExposure, ApplySelectedResponse,
    EnterSelectedRemediation, ContinueSelectedScore,
)


class CompletionContinuations:
    def __init__(self, *, source_identity, notices, teaching_continuation,
                 attempt_settlement, playback_session, visual_transport,
                 attempt, flow_session, lesson_execution, transport_timing,
                 score_read, recovery_workflows, timed_playback,
                 lesson_cursor, teaching_decisions, clock, library,
                 score_artifact_registry, assessment, feedback_seconds):
        self.source_identity, self.notices = source_identity, notices
        self.teaching_continuation, self.attempt_settlement = teaching_continuation, attempt_settlement
        self.playback_session, self.visual_transport = playback_session, visual_transport
        self.attempt, self.flow_session = attempt, flow_session
        self.lesson_execution, self.transport_timing = lesson_execution, transport_timing
        self.score_read, self.recovery_workflows = score_read, recovery_workflows
        self.timed_playback = timed_playback
        self.lesson_cursor, self.teaching_decisions = lesson_cursor, teaching_decisions
        self.clock, self.library = clock, library
        self.score_artifact_registry = score_artifact_registry
        self.assessment, self.feedback_seconds = assessment, feedback_seconds

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
            self.commit_pending(finish_publication=False)
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

    def commit_pending(self, *, finish_publication: bool = True) -> str:
        if self.attempt_settlement.pending_result is None or self.source_identity.plan is None:
            return ""
        pending = self.attempt_settlement.pending
        if pending.phase == "effects_applied":
            # The teaching receipt and its score/revision effects already
            # committed. A later continuation failure may retry from that
            # receipt, but must never replay stage adoption or rewind.
            if finish_publication:
                self.attempt_settlement.finish_publication()
            self.attempt.publication_finished()
            return pending.publication.receipt.message
        decision = pending.decision
        try:
            committed = self.attempt_settlement.commit_full_passage(
                plan=self.source_identity.plan,binding=self.teaching_decisions.binding(),now=self.clock(),
                continuation=self.teaching_continuation,
                policy=resolve_mistake_policy(self.library.settings["mistake_response_strategy"]),
                score_revision=self.source_identity.revision,
                visual_offset=self.visual_transport.visual_offset_beats)
            outcome = committed.receipt
            self.attempt.apply_settlement(committed,plan=self.source_identity.plan)
            if decision.verdict is not None and decision.verdict.clears_trouble:
                self.lesson_execution.reset_trouble()
            if outcome.stage_changed:
                self.lesson_cursor.select_opening(0.0)
                self.source_identity.publish_revision(committed.selection.revision)
                self.playback_session.wait_for_player()
                prebuilt = self.teaching_continuation.consume_committed_asset(
                    committed.prepared,changed=True,auto=self.playback_session.auto,
                    selection=committed.selection)
                if prebuilt is not None:
                    self.score_artifact_registry.adopt(prebuilt)
                else:
                    self.score_artifact_registry.current.invalidate()
                self.visual_transport.adopt_committed_stage(
                    committed,preserved=prebuilt is not None)
            else:
                self.teaching_continuation.consume_committed_asset(
                    None,changed=False,auto=self.playback_session.auto,selection=None)
        except BaseException:
            self.attempt.publication_failed()
            raise
        self.attempt_settlement.effects_applied(pending)
        if finish_publication:
            self.attempt_settlement.finish_publication()
        self.attempt.publication_finished()
        return outcome.message

    def performance_review(self, phrase: Phrase, result) -> dict:
        """Retained engine API; assessment service owns report construction."""
        tempo = self.transport_timing.active_tempo_map()
        elapsed_to_beat = (None if tempo is None else
            lambda seconds: tempo.beat_at(tempo.seconds_at(self.visual_transport.play_from_beat)+seconds))
        return self.assessment.review(
            phrase, result, bar_boundaries=self.source_identity.plan.piece.bar_boundaries,
            played_from_beat=self.visual_transport.play_from_beat, bpm=self.source_identity.plan.bpm,
            elapsed_to_beat=elapsed_to_beat)

    def finish_performance_review(self, phrase: Phrase, result):
        """Publish review only after its evidence and source feedback commit."""
        self.notices.next_action = performance_next_action(
            warmup=self.source_identity.warmup,summary=self.attempt.performance_summary)
        self.playback_session.stop_automatic()

    def finish_section_review(self, result):
        """Complete finish section review after a scored take."""
        # Section reviews are deliberate, bounded practice. Stop at the
        # selected boundary, preserve detailed feedback, and never
        # auto-advance to a different passage.
        self.playback_session.stop_automatic()
        self.attempt.finish_section_review()
        self.visual_transport.finish_rewind()
        self.lesson_cursor.select_opening(0.0)
        self.notices.feedback = "Section review finished · " + result.summary
        self.notices.next_action = "Review the notes or press Start for the whole passage."

    def finish_partial_recovery(self, result, now: float, *, exposure=None):
        """Complete finish partial recovery after a scored take."""
        # A clean *partial* recovery cannot confer full passage mastery.
        # Clear the bounded review before the scheduled full-pass retry.
        self.attempt.prepare_full_retry()
        self.lesson_cursor.select_opening(exposure.from_beat if exposure is not None else 0.0)
        self.transport_timing.schedule_preparation(self.lesson_cursor.opening_beat, now=now,
            from_visual=self.visual_transport.visual_offset_beats + self.visual_transport.play_from_beat
                + self.transport_timing.elapsed_beat(now-self.visual_transport.run_at),
            reverse_seconds=self.feedback_seconds)
        self.notices.feedback = "Selected section finished · " + result.summary
        self.notices.next_action = "Next: play the whole passage from its beginning to earn mastery."


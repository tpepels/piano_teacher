"""The durable successor of a full passage: feedback, commit, effect.

A full passage settles at its successor boundary. This class owns that
transaction: wait for feedback and assets, commit the selected decision
(SQLite receipt, stage adoption), then dispatch its typed, source-bound
effect exactly once. A failed effect leaves the receipt retryable.
"""
from __future__ import annotations
from ..lesson_settings import SETTINGS
from .playback_facts import FullPassageFacts
from .teaching_continuation import (
    UnpreparedNextStage, FeedbackWaiting, FeedbackFault,
    SettledSourceFacts, EnterSelectedExposure, ApplySelectedResponse,
    EnterSelectedRemediation, ContinueSelectedScore,
)


class SettlementContinuation:
    def __init__(self, *, lesson, notices, score, take, transport,
                 lesson_execution, transport_timing, selected_recovery,
                 continuation, mistake_policy):
        self.lesson = lesson
        self.notices = notices
        self.score = score
        self.take = take
        self.transport = transport
        self.lesson_execution = lesson_execution
        self.transport_timing = transport_timing
        self.selected_recovery = selected_recovery
        self.continuation = continuation
        self.mistake_policy = mistake_policy
        # Successful effects are consumed by their exact durable identity.
        # A continuation dispatch error leaves the receipt retryable.
        self._applied_continuation_effect = None

    def feedback_due(self, now: float) -> bool:
        """The feedback interval ended; return whether a follow-up is queued."""
        publication = self.take.pending_full_completion
        if publication is not None:
            return self.finish_full_passage(publication.result,
                publication.total_beats,publication.duration,now)
        self.advance_pending_feedback(now)
        return False

    def advance_pending_feedback(self, now: float, *, force_early: bool = False,
                                 explicit_retry: bool = False):
        # Worker ticks must not spin on a failed committed effect after
        # automatic playback was stopped. Only the user-facing Retry route
        # may re-enter that already-selected feedback transaction.
        if not self.transport.auto and not explicit_retry:
            return
        transaction = self.score.begin_feedback(
            self.take.pending, now=now,
            automatic=self.transport.auto or explicit_retry,
            force_early=force_early, revision=self.lesson.revision,
            fingerprint=self.lesson.fingerprint)
        if isinstance(transaction,FeedbackWaiting):
            if transaction.message:
                self.notices.feedback = transaction.message
            return
        if isinstance(transaction,FeedbackFault):
            self.publish_feedback_fault(transaction,now)
            return
        try:
            self.commit_pending(now, finish_publication=False)
            self.transport.note_tempo(
            stage=self.lesson.plan.identity,bpm=self.transport_timing.presentation_bpm(),now=now)
        except Exception as exc:
            pending = self.take.pending
            self.publish_feedback_fault(self.score.settlement_failure(
                exc,saved=pending is not None and pending.receipt is not None),now)
            if not isinstance(exc,UnpreparedNextStage):
                print("ASSESSMENT_SETTLEMENT_FAILED:",type(exc).__name__,str(exc),flush=True)
            return
        # The assessment is durable, but the selected successor has not
        # yet been applied. Retain its visible note feedback until the
        # exact source-bound continuation is successfully installed.
        try:
            publication = self.score.finish_feedback(
                transaction, SettledSourceFacts(
                    fingerprint=self.lesson.fingerprint,
                    stage_key=self.lesson.plan.identity,
                    revision=self.lesson.revision,
                    now=now, bpm=self.lesson.plan.bpm,
                    presentation_bpm=self.transport_timing.presentation_bpm(),
                    count_in_beats=self.transport_timing.next_count_in_beats(),
                    automatic=transaction.pending.state.route.automatic,
                    flow_active=self.lesson_execution.flow_active()))
            if publication.flow_outcome is not None:
                self.lesson.settle_flow_decision(
                    publication.flow_outcome, plan=self.lesson.plan,
                    message=publication.message, decision_id=transaction.decision_id)
            if explicit_retry and transaction.pending.state.route.automatic:
                # Only an explicitly requested retry restores the original
                # automatic course intent; a failed effect below stops it
                # again. The committed decision, not current UI mode, owns
                # whether this continuation should run automatically.
                self.transport.continue_course()
            with self.take.publishing(transaction.pending):
                self.dispatch_effect(publication.effect, now)
                # Visible marks are retained until the exact physical/source
                # continuation has been installed successfully. Source
                # installation can cancel its predecessor's take, but the
                # original durable receipt must survive through this ACK.
                self.take.clear_feedback()
                self.take.finish_publication()
        except Exception as exc:
            # The settled take and receipt remain committed. Make an
            # explicit Retry re-enter this selected transaction; do not
            # silently select a new source or grade a second attempt.
            self.take.publication_failed()
            self.transport.stop_automatic()
            self.notices.feedback = "Progress saved, but the next step could not start"
            self.notices.next_action = "Press Play to continue from the same saved result."
            print("CONTINUATION_EFFECT_FAILED:", type(exc).__name__, str(exc), flush=True)

    def retry_failed_publication(self, *, now: float) -> str:
        """Retry the original full result, including its retained effects."""
        pending = self.take.pending
        if (pending is None or pending.event.kind != "full_result"
                or pending.phase == "published"):
            raise ValueError("No interrupted full-passage settlement to retry")
        self.advance_pending_feedback(
            now, force_early=True, explicit_retry=True)
        if pending.phase != "published" or pending.receipt is None:
            raise RuntimeError("Selected assessment continuation is still pending")
        return pending.receipt.message

    def publish_feedback_fault(self, fault: FeedbackFault, now: float) -> None:
        self.transport.apply_feedback_fault(fault,now=now)
        self.notices.feedback,self.notices.next_action = fault.feedback,fault.next_action

    def finish_full_passage(self, result, total_beats: float, duration: float, now: float):
        publication = self.take.begin_full_completion(
            result,total_beats=total_beats,duration=duration)
        pending = publication.pending
        total_beats,duration = publication.total_beats,publication.duration
        self.take.checkpoint_failed_streak(pending,plan=self.lesson.plan,now=now)
        self.transport.note_tempo(
            stage=self.lesson.plan.identity,bpm=self.transport_timing.presentation_bpm(),now=now)
        exposure = pending.decision.next_exposure
        target = exposure.from_beat if exposure is not None else self.transport.play_from_beat
        completion = self.transport.finish_full_passage(FullPassageFacts(
            pending=pending,stage_key=self.lesson.plan.identity,bpm=self.lesson.plan.bpm,
            target_bpm=self.lesson.plan.target_bpm,
            assessed_bpm=self.take.pending_assessed_bpm,
            total_beats=total_beats,duration=duration,now=now,
            visual_from=self.transport_timing.visual_motion(now)[0],feedback_seconds=SETTINGS.feedback_seconds,
            source_model=self.score.source_model(),presentation_bpm=self.transport_timing.presentation_bpm(),
            horizon_beats=self.transport.continuous_horizon_beats,warmup=self.lesson.warmup,
            short_rest_enabled=self.transport.short_rest is not None,
            retry_rest=self.transport_timing.collect_rest_measurement(from_beat=target),
            repeat_rest=self.transport_timing.collect_rest_measurement(from_beat=0.0,
                source_end=self.transport.run_at+duration),
            assets_ready=self.score.decision_assets_ready(pending,
                revision=self.lesson.revision,fingerprint=self.lesson.fingerprint),
            exact_repeats=self.lesson_execution.flow_active()))
        if completion.next_action is not None:
            self.notices.next_action = completion.next_action
        if completion.advance_feedback:
            self.advance_pending_feedback(now,force_early=completion.force_early)
        elif completion.update_clock:
            self.take.finish_full_completion(publication)
            return True
        self.take.finish_full_completion(publication)
        return False

    def dispatch_effect(self, effect, now: float) -> None:
        """Apply a committed successor only to its exact installed source.

        This guard is deliberately at the effect boundary: an ACK, Stop or
        source replacement can supersede a publication after a decision was
        durably settled but before the native continuation starts.
        """
        pending = self.take.pending
        identity = effect.identity
        plan = self.lesson.plan
        if (pending is None or plan is None
                or pending.decision.decision_id != identity.decision_id
                or pending.receipt is None
                or pending.phase not in ("effects_applied", "published")
                or identity.fingerprint != self.lesson.fingerprint
                or identity.stage_key != plan.identity
                or identity.revision != self.lesson.revision):
            raise ValueError("Stale or unsettled teaching continuation effect")
        previous = self._applied_continuation_effect
        if previous is not None and previous.identity == effect.identity:
            if previous != effect:
                raise ValueError("Conflicting continuation effects for one decision")
            return
        if isinstance(effect,EnterSelectedExposure):
            self.lesson_execution.enter_selected_exposure(effect.exposure)
        elif isinstance(effect,ApplySelectedResponse):
            self.selected_recovery.apply_policy_response(effect.response,now=now,deadline=effect.deadline)
        elif isinstance(effect,EnterSelectedRemediation):
            self.selected_recovery.start_remedial_assignment(effect.assignment,deadline=effect.deadline,
                exposure=effect.exposure)
        else:
            if isinstance(effect,ContinueSelectedScore):
                applied = self.transport.apply_continuation(effect,
                    measurement=self.transport_timing.collect_continuation_measurement(
                        effect.deadline,effect.exposure.from_beat),
                    source_stride_beats=self.score.source_model()["practice_timeline"]["stride_beats"])
            else:
                applied = self.transport.apply_continuation(effect)
            if applied.feedback is not None:
                self.notices.feedback = applied.feedback
            if applied.start is not None:
                self.continuation.continue_at(applied.start.deadline,from_beat=applied.start.from_beat)
        # Record success after every domain and physical start effect.
        # If any action raises, the same settlement receipt can replay it.
        self._applied_continuation_effect = effect

    def commit_pending(self, now: float, *, finish_publication: bool = True) -> str:
        if self.take.pending_result is None or self.lesson.plan is None:
            return ""
        pending = self.take.pending
        if pending.phase == "effects_applied":
            # The teaching receipt and its score/revision effects already
            # committed. A later continuation failure may retry from that
            # receipt, but must never replay stage adoption or rewind.
            if finish_publication:
                self.take.finish_publication()
            self.take.publication_finished()
            return pending.publication.receipt.message
        decision = pending.decision
        try:
            committed = self.take.commit_full_passage(
                plan=self.lesson.plan,binding=self.lesson.decision_binding(),now=now,
                continuation=self.score,
                policy=self.mistake_policy(),
                score_revision=self.lesson.revision,
                visual_offset=self.transport.visual_offset_beats)
            outcome = committed.receipt
            self.take.apply_settlement(committed,plan=self.lesson.plan)
            if decision.verdict is not None and decision.verdict.clears_trouble:
                self.lesson_execution.reset_trouble()
            if outcome.stage_changed:
                self.lesson.select_opening(0.0)
                self.lesson.publish_revision(committed.selection.revision)
                self.transport.wait_for_player()
                prebuilt = self.score.consume_committed_asset(
                    committed.prepared,changed=True,auto=self.transport.auto,
                    selection=committed.selection)
                if prebuilt is not None:
                    self.score.adopt_artifacts(prebuilt)
                else:
                    self.score.current_artifacts.invalidate()
                self.transport.adopt_committed_stage(
                    committed,preserved=prebuilt is not None)
            else:
                self.score.consume_committed_asset(
                    None,changed=False,auto=self.transport.auto,selection=None)
        except BaseException:
            self.take.publication_failed()
            raise
        self.take.effects_applied(pending)
        if finish_publication:
            self.take.finish_publication()
        self.take.publication_finished()
        return outcome.message

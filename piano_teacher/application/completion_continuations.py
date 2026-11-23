"""Apply settled teaching continuation and exact feedback effects.

Accepts the sole AttemptSettlement receipt; applies typed, already-decided
successor effects. Does not choose an alternate stage, deadline or grade.
"""
from __future__ import annotations
from .playback_facts import FullPassageFacts
from ..music import Phrase
from .mistake_responses import resolve_mistake_policy
from .passage_outcome_presenter import performance_next_action
from .teaching_continuation import (
    UnpreparedNextStage, FeedbackWaiting, FeedbackFault,
    SettledSourceFacts, EnterSelectedExposure, ApplySelectedResponse,
    EnterSelectedRemediation, ContinueSelectedScore,
)


class CompletionContinuations:
    def __init__(self, *, lesson, notices, score, take, transport,
                          lesson_execution, transport_timing,
                          recovery_workflows, timed_playback, clock, library,
                          assessment, feedback_seconds, policy_registry,
                          live_assessment, live_feedback_workflows, measurement):
        self.policy_registry, self.live_assessment = policy_registry, live_assessment
        self.live_feedback_workflows, self.measurement = live_feedback_workflows, measurement
        self.notices = notices
        self.lesson = lesson
        self.score = score
        self.take = take
        self.transport = transport
        self.lesson_execution, self.transport_timing = lesson_execution, transport_timing
        self.recovery_workflows = recovery_workflows
        self.timed_playback = timed_playback
        self.clock, self.library = clock, library
        self.assessment, self.feedback_seconds = assessment, feedback_seconds
        # Successful effects are consumed by their exact durable identity.
        # A continuation dispatch error leaves the receipt retryable.
        self._applied_continuation_effect = None

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
            self.commit_pending(finish_publication=False)
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

    def complete_take(self, phrase: Phrase, ending: float,
                          total_beats: float, duration: float, now: float) -> bool:
        """Apply post-performance state after the score's settlement interval.

        Called from PracticeSession's locked event drain. Assessment
        and grading occur only after a completed non-preview take.
        Returns whether another same-tick transition must be queued.
        """
        self.transport.record_take_end(
            at=self.transport.run_at + duration,
            bpm=self.lesson.plan.bpm)
        if self.transport.preview_only:
            # Disconnected MIDI: repeat as an ungraded preview, never create
            # fake notes, misses, accepted passes or mastery.
            self.take.finish_preview()
            self.transport.finish_take()
            self.transport.schedule_preview_repeat(
                source_seconds=duration,source_bpm=self.lesson.plan.bpm,
                presentation_bpm=self.transport_timing.presentation_bpm(),
                rest_measurement=self.transport_timing.collect_rest_measurement(
                    from_beat=0.0,
                    source_end=self.transport.run_at+duration),
                now=now,reading_horizon_beats=self.transport.continuous_horizon_beats)
            self.notices.feedback = "Timing preview - repeating after one empty measure"
            self.notices.next_action = "Connect your MIDI piano to earn progress."
            # The next preview must be admitted during the rest, not at
            # the previous retry deadline after its count-in is over.
            self.timed_playback.continue_at(self.transport.next_at,
                from_beat=0.0)
            return False
        completed_visual = self.transport_timing.visual_motion(now)[0]
        completed = self.take.complete_take(
            phrase=phrase,hand=self.lesson.plan.hand,bpm=self.lesson.plan.bpm,
            played=(self.take.recorder.presses
                    if self.take.recorder else ()),
            from_beat=self.transport.play_from_beat,end_beat=ending,
            tempo=self.transport_timing.active_tempo_map(),policies=self.policy_registry.grading,
            layout_for_feedback=self.score.completed_take_layout,
            mode=self.transport.mode,review_end_beat=self.take.review_end_beat,
            automatic_remedial_review=self.take.automatic_remedial_review,
            performance_review=self.performance_review,
            prepare_decision=self.lesson.prepare_decision,
            plan=self.lesson.plan,binding=self.lesson.decision_binding(),now=now,
            score_revision=self.lesson.revision,
            policy=resolve_mistake_policy(
                self.library.settings["mistake_response_strategy"]))
        assessed = completed.assessed
        result,summary = assessed.result,completed.summary
        if completed.settled:
            self.transport.note_tempo(
            stage=self.lesson.plan.identity,bpm=self.transport_timing.presentation_bpm(),now=now)
        self.take.publish_completion(
            marks=assessed.marks,unmapped=assessed.unmapped)
        # The completed take's settled grades, before any transition below can
        # start another transport.
        self.live_assessment.publish(self.take.feedback_marks, self.live_feedback_workflows.feedback_take(),
                                     final=True)
        self.notices.feedback = assessed.feedback
        self.transport.finish_take()
        self.take.finish_review(summary,self.lesson.plan.identity)
        self.measurement.phase_changed("feedback", now)
        if not self.apply_focused(
                completed.effect, phrase=phrase, result=result, now=now,
                visual_from=completed_visual):
            return self.finish_full_passage(result,total_beats,duration,now)
        return False

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
            visual_from=self.transport_timing.visual_motion(now)[0],feedback_seconds=self.feedback_seconds,
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

    def apply_focused(self, effect, *, phrase, result, now: float,
                      visual_from: float) -> bool:
        """Apply one immediately settled focused/performance consequence.

        Returns False for a full passage, whose consequence is applied by
        dispatch_effect only after its durable successor boundary.
        """
        if effect.action == "response":
            self.recovery_workflows.apply_policy_response(
                effect.response,now=now,visual_from=visual_from)
        elif effect.action == "perform":
            self.finish_performance_review(phrase,result)
        elif effect.action == "section_review":
            self.finish_section_review(result)
        elif effect.action == "stop_review":
            self.transport.halt_continuation()
            self.notices.next_action = "Review this section before starting another take."
        elif effect.action == "exposure":
            self.lesson_execution.enter_selected_exposure(effect.exposure)
        elif effect.action == "partial_recovery":
            self.finish_partial_recovery(result,now,exposure=effect.exposure)
        elif effect.action == "full_passage":
            return False
        else:
            raise ValueError(f"Unknown completion consequence {effect.action!r}")
        return True

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
            self.recovery_workflows.apply_policy_response(effect.response,now=now,deadline=effect.deadline)
        elif isinstance(effect,EnterSelectedRemediation):
            self.recovery_workflows.start_remedial_assignment(effect.assignment,deadline=effect.deadline,
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
                self.timed_playback.continue_at(applied.start.deadline,from_beat=applied.start.from_beat)
        # Record success after every domain and physical start effect.
        # If any action raises, the same settlement receipt can replay it.
        self._applied_continuation_effect = effect

    def commit_pending(self, *, finish_publication: bool = True) -> str:
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
                plan=self.lesson.plan,binding=self.lesson.decision_binding(),now=self.clock(),
                continuation=self.score,
                policy=resolve_mistake_policy(self.library.settings["mistake_response_strategy"]),
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

    def performance_review(self, phrase: Phrase, result) -> dict:
        """Retained engine API; assessment service owns report construction."""
        tempo = self.transport_timing.active_tempo_map()
        elapsed_to_beat = (None if tempo is None else
            lambda seconds: tempo.beat_at(tempo.seconds_at(self.transport.play_from_beat)+seconds))
        return self.assessment.review(
            phrase, result, bar_boundaries=self.lesson.plan.piece.bar_boundaries,
            played_from_beat=self.transport.play_from_beat, bpm=self.lesson.plan.bpm,
            elapsed_to_beat=elapsed_to_beat)

    def finish_performance_review(self, phrase: Phrase, result):
        """Publish review only after its evidence and source feedback commit."""
        self.notices.next_action = performance_next_action(
            warmup=self.lesson.warmup,summary=self.take.performance_summary)
        self.transport.stop_automatic()

    def finish_section_review(self, result):
        """Complete finish section review after a scored take."""
        # Section reviews are deliberate, bounded practice. Stop at the
        # selected boundary, preserve detailed feedback, and never
        # auto-advance to a different passage.
        self.transport.stop_automatic()
        self.take.finish_section_review()
        self.transport.finish_rewind()
        self.lesson.select_opening(0.0)
        self.notices.feedback = "Section review finished · " + result.summary
        self.notices.next_action = "Review the notes or press Start for the whole passage."

    def finish_partial_recovery(self, result, now: float, *, exposure=None):
        """Complete finish partial recovery after a scored take."""
        # A clean *partial* recovery cannot confer full passage mastery.
        # Clear the bounded review before the scheduled full-pass retry.
        self.take.prepare_full_retry()
        self.lesson.select_opening(exposure.from_beat if exposure is not None else 0.0)
        self.transport_timing.schedule_preparation(self.lesson.opening_beat, now=now,
            from_visual=self.transport.visual_offset_beats + self.transport.play_from_beat
                + self.transport_timing.elapsed_beat(now-self.transport.run_at),
            reverse_seconds=self.feedback_seconds)
        self.notices.feedback = "Selected section finished · " + result.summary
        self.notices.next_action = "Next: play the whole passage from its beginning to earn mastery."


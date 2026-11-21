"""Single monotonic-worker application workflow for completed takes and transitions.

The engine lock is held by the public worker/command boundary. This class
applies the accepted stage, assessment, recording and admission effects;
the underlying owners retain their one authoritative decision and clock.
"""
from __future__ import annotations
import logging
from ..music import Phrase
from .playback_facts import TimedTakeSource, FullPassageFacts
from .practice_transitions import TransitionContext, decide_transition
from .attempt_progression import AttemptTick
from .learning_capture import CapturePhaseFacts
from .musical_scheduler import SCHEDULER
from .mistake_responses import resolve_mistake_policy
from . import practice_flow


class PracticeTimeline:
    def __init__(self, *, source_identity, notices,
                 visual_transport, playback_session, playback,
                 attempt_settlement, attempt, transport_timing, timed_playback,
                 score_read, outcome_effects, lesson_execution,
                 recovery_workflows, completion_continuations,
                 live_feedback_workflows, live_assessment, measurement,
                 policy_registry, library, teaching_decisions,
                 guided_session, flow_session, midi, listen, midi_ingress,
                 midi_calibration, attempt_progression, read_models,
                 teaching_continuation, exposure_workflows,
                 clock, poll_midi, feedback_seconds):
        self.source_identity, self.notices = source_identity, notices
        self.visual_transport, self.playback_session, self.playback = visual_transport, playback_session, playback
        self.attempt_settlement, self.attempt = attempt_settlement, attempt
        self.transport_timing, self.timed_playback = transport_timing, timed_playback
        self.score_read, self.outcome_effects = score_read, outcome_effects
        self.lesson_execution, self.recovery_workflows = lesson_execution, recovery_workflows
        self.completion_continuations = completion_continuations
        self.live_feedback_workflows, self.live_assessment = live_feedback_workflows, live_assessment
        self.measurement, self.policy_registry = measurement, policy_registry
        self.library, self.teaching_decisions = library, teaching_decisions
        self.guided_session, self.flow_session = guided_session, flow_session
        self.midi, self.listen, self.midi_ingress = midi, listen, midi_ingress
        self.midi_calibration, self.attempt_progression = midi_calibration, attempt_progression
        self.read_models, self.clock, self.poll_midi = read_models, clock, poll_midi
        self.teaching_continuation, self.exposure_workflows = teaching_continuation, exposure_workflows
        self.feedback_seconds = feedback_seconds
        # An accepted continuation can request another transition in this
        # same locked tick, never another nested worker/tick invocation.
        self._pending_immediate_transitions = 0

    def complete_attempt(self, phrase: Phrase, ending: float,
                          total_beats: float, duration: float, now: float) -> None:
        """Apply post-performance state after the score's settlement interval.

        This method is called from the locked _update loop. Assessment and
        grading are calculated only after a completed non-preview take.
        """
        self.visual_transport.rest_take_end = (self.visual_transport.run_at + duration, self.source_identity.plan.bpm)
        if self.playback_session.preview_only:
            # Disconnected MIDI: repeat as an ungraded preview, never create
            # fake notes, misses, accepted passes or mastery.
            self.attempt_settlement.finish_preview()
            self.playback_session.finish_take()
            self.visual_transport.schedule_preview_repeat(
                source_seconds=duration,source_bpm=self.source_identity.plan.bpm,
                presentation_bpm=self.transport_timing.presentation_bpm(),
                rest_measurement=self.transport_timing.collect_rest_measurement(
                    from_beat=0.0,
                    source_end=self.visual_transport.run_at+duration),
                now=now,reading_horizon_beats=self.visual_transport.continuous_horizon_beats)
            self.notices.feedback = "Timing preview - repeating after one empty measure"
            self.notices.next_action = "Connect your MIDI piano to earn progress."
            if self.playback.presentation_required:
                # The next preview must be admitted during the rest, not at
                # the previous retry deadline after its count-in is over.
                self.timed_playback.continue_at(self.visual_transport.next_at,
                    from_beat=0.0)
            elif now >= self.visual_transport.next_at:
                self._request_immediate_transition()
            return
        completed_visual = self.transport_timing.visual_motion(now)[0]
        completed = self.attempt_settlement.complete_take(
            phrase=phrase,hand=self.source_identity.plan.hand,bpm=self.source_identity.plan.bpm,
            played=(self.attempt.recorder.presses
                    if self.attempt.recorder else ()),
            from_beat=self.visual_transport.play_from_beat,end_beat=ending,
            tempo=self.transport_timing.active_tempo_map(),policies=self.policy_registry.grading,
            layout_for_feedback=self.score_read.completed_take_layout,
            mode=self.playback_session.mode,review_end_beat=self.attempt.review_end_beat,
            automatic_remedial_review=self.attempt.automatic_remedial_review,
            performance_review=self.outcome_effects.performance_review,
            prepare_decision=self.teaching_decisions.prepare,
            plan=self.source_identity.plan,binding=self.teaching_decisions.binding(),now=now,
            policy=resolve_mistake_policy(
                self.library.settings["mistake_response_strategy"]))
        assessed = completed.assessed
        result,route,summary = assessed.result,completed.route,completed.summary
        pending,response,settled = (
            completed.pending,completed.response,completed.settled)
        if settled:
            self.visual_transport.note_tempo(
            stage=self.source_identity.plan.identity,bpm=self.transport_timing.presentation_bpm(),now=now)
        self.attempt.publish_completion(
            marks=assessed.marks,unmapped=assessed.unmapped)
        # The completed take's settled grades, before any transition below can
        # start another transport.
        self.live_assessment.publish(self.attempt.feedback_marks, self.live_feedback_workflows.feedback_take(),
                                     final=True)
        self.notices.feedback = assessed.feedback
        self.playback_session.finish_take()
        self.attempt.finish_review(summary,self.source_identity.plan.identity)
        self.measurement.phase_changed("feedback", now)
        effect = completed.effect
        if effect.action == "response":
            self.recovery_workflows.apply_policy_response(effect.response,now=now,visual_from=completed_visual)
        elif effect.action == "perform":
            self.outcome_effects.finish_performance_review(phrase,result)
        elif effect.action == "section_review":
            self.outcome_effects.finish_section_review(result)
        elif effect.action == "stop_review":
            self.playback_session.stop_automatic()
            self.visual_transport.cancel_preparation()
            self.visual_transport.cancel_continuation()
            self.notices.next_action = "Review this section before starting another take."
        elif effect.action == "exposure":
            self.lesson_execution.enter_selected_exposure(effect.exposure)
        elif effect.action == "partial_recovery":
            self.outcome_effects.finish_partial_recovery(result,now,exposure=effect.exposure)
        else:
            self.finish_full_passage(result,total_beats,duration,now)

    def finish_full_passage(self, result, total_beats: float, duration: float, now: float):
        publication = self.attempt_settlement.begin_full_completion(
            result,total_beats=total_beats,duration=duration)
        pending = publication.pending
        total_beats,duration = publication.total_beats,publication.duration
        self.attempt_settlement.checkpoint_failed_streak(pending,plan=self.source_identity.plan,now=now)
        self.visual_transport.note_tempo(
            stage=self.source_identity.plan.identity,bpm=self.transport_timing.presentation_bpm(),now=now)
        exposure = pending.decision.next_exposure
        target = exposure.from_beat if exposure is not None else self.visual_transport.play_from_beat
        completion = self.playback_session.finish_full_passage(FullPassageFacts(
            pending=pending,stage_key=self.source_identity.plan.identity,bpm=self.source_identity.plan.bpm,
            target_bpm=self.source_identity.plan.target_bpm,
            assessed_bpm=self.attempt_settlement.pending_assessed_bpm,
            total_beats=total_beats,duration=duration,now=now,
            visual_from=self.transport_timing.visual_motion(now)[0],feedback_seconds=self.feedback_seconds,
            source_model=self.score_read.source_model(),presentation_bpm=self.transport_timing.presentation_bpm(),
            horizon_beats=self.visual_transport.continuous_horizon_beats,warmup=self.source_identity.warmup,
            presentation_required=self.playback.presentation_required,
            short_rest_enabled=self.visual_transport.short_rest is not None,
            retry_rest=self.transport_timing.collect_rest_measurement(from_beat=target),
            repeat_rest=self.transport_timing.collect_rest_measurement(from_beat=0.0,
                source_end=self.visual_transport.run_at+duration),
            assets_ready=self.teaching_continuation.decision_assets_ready(pending,
                revision=self.source_identity.revision,fingerprint=self.source_identity.fingerprint),
            exact_repeats=self.lesson_execution.flow_active()))
        if completion.next_action is not None:
            self.notices.next_action = completion.next_action
        if completion.advance_feedback:
            self.completion_continuations.advance_pending_feedback(now,force_early=completion.force_early)
        elif completion.update_clock:
            self.attempt_settlement.finish_full_completion(publication)
            self._request_immediate_transition()
            return
        self.attempt_settlement.finish_full_completion(publication)

    def run_pre_assessment_transition(self, now: float) -> bool:
        """Apply an explicit non-grading transition under the session lock."""
        if self.playback.presentation_required and self.playback.intent is not None:
            return True
        context = TransitionContext(
            has_plan=self.source_identity.plan is not None,
            learning=self.playback_session.mode == "learn" and self.guided_session.controller is not None,
            paused=self.visual_transport.paused, listening=self.playback_session.mode == "listen",
            preview_pending=self.visual_transport.preview_loop_pending,
            preparation_pending=self.visual_transport.preparation_pending,
            feedback_pending=self.attempt_settlement.feedback_pending,
            awaiting_score=self.playback_session.awaiting_score_revision is not None,
            rewind_pending=self.visual_transport.pending_rewind is not None,
            running=self.playback_session.running, run_at=self.visual_transport.run_at)
        decision = decide_transition(
            context, now=now, next_at=self.visual_transport.next_at,
            preparation_at=self.visual_transport.preparation_deadline)
        if decision.preparation_phase is not None:
            self.visual_transport.enter_preparation_phase(decision.preparation_phase)
        if decision.action == "learning":
            self.guided_session.advance(connected=self.midi.connected, now=now)
            self.lesson_execution.save_guided_preparation()
        elif decision.action == "listening":
            if self.playback_session.running and self.listen.finished(now=now, run_at=self.visual_transport.run_at):
                self.playback_session.finish_take()
                self.notices.feedback = "Example complete"
                self.notices.next_action = (
                    "Choose Learn to find the notes, or Practice to play the rhythm.")
                if (self.lesson_execution.flow_active() and self.flow_session.state is not None
                        and self.flow_session.state.step is practice_flow.Step.LISTEN):
                    self.lesson_execution.flow_execute(self.flow_session.listen_finished())
        elif decision.action == "preview_due":
            deadline = self.visual_transport.next_at
            self.visual_transport.advance_source_stride(self.score_read.source_model()[
                "practice_timeline"]["stride_beats"])
            self.timed_playback.continue_at(SCHEDULER.continuation(
                    self.transport_timing.collect_continuation_measurement(deadline, 0.0),
                    now=self.clock(),bpm=self.transport_timing.presentation_bpm()))
        elif decision.action == "feedback":
            publication = self.attempt_settlement.pending_full_completion
            if publication is not None:
                self.finish_full_passage(publication.result,
                    publication.total_beats,publication.duration,now)
            else:
                self.completion_continuations.advance_pending_feedback(now)
        elif decision.action == "rewind_due":
            if self.attempt.guided_recovery_pending:
                self.lesson_execution.begin_learn(from_beat=self.visual_transport.pending_rewind, recovery=True,
                    exposure=self.attempt_settlement.pending.decision.next_exposure)
            else:
                target = self.visual_transport.pending_rewind
                self.timed_playback.continue_at(
                    SCHEDULER.continuation(
                    self.transport_timing.collect_continuation_measurement(self.visual_transport.next_at, target),
                    now=self.clock(),bpm=self.transport_timing.presentation_bpm()),
                    from_beat=target)
        return decision.consumed

    def _request_immediate_transition(self) -> None:
        """Defer a nested completion/preview update to this worker's loop."""
        self._pending_immediate_transitions += 1

    def update(self) -> None:
        # Two continuation cases used to recursively call update() while the
        # single native musical tick was already executing. Drain those
        # requests before publishing, preserving their deepest-first publish
        # order. Bound anomalous cycles instead of growing the Python stack.
        nested = 0
        try:
            while True:
                self._pending_immediate_transitions = 0
                self.update_transition()
                requests = self._pending_immediate_transitions
                if requests == 0:
                    break
                nested += requests
                if nested > 16:
                    raise RuntimeError(
                        "Practice transitions exceeded the bounded same-tick handoff")
        except Exception:
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=self.clock())
            self.notices.feedback = "Could not save or finish the practice transition"
            self.notices.next_action = (
                "Check storage or the reported error, then Resume to retry this same take.")
            raise

        # Previously each recursively entered update published on the way out,
        # then its caller published again. Apply that same number of outer
        # publications without re-running a command/tick or another clock.
        for _ in range(nested + 1):
            self.playback.advance(self.transport_timing.playback_facts())
            self.read_models.prepare_score_presentation()
            try:
                self.live_feedback_workflows.publish_live()
            except Exception:
                logging.getLogger(__name__).exception(
                    "Live assessment publication failed; skipping this tick")

    def update_transition(self) -> None:
        """Advance the backend clock under its existing session lock."""
        self.poll_midi()
        self.midi_calibration.advance(self.clock())
        self.exposure_workflows.apply_listen_failure()
        now = self.clock()
        learning = self.playback_session.mode == "learn"
        guided_completed = bool(
            learning and self.guided_session.controller is not None
            and self.guided_session.controller.snapshot(now=now)["completed"])
        self.measurement.observe_phase(CapturePhaseFacts(
            paused=self.visual_transport.paused,learning=learning,
            awaiting_score=self.playback_session.awaiting_score_revision is not None,
            guided_completed=guided_completed,running=self.playback_session.running,
            count_in_activation=max(
                self.visual_transport.run_at,
                self.midi_ingress.resume_grading_after),
            mode=self.playback_session.mode,preview=self.playback_session.preview_only,
            pending_result=self.attempt_settlement.pending_result is not None,
            preparation_pending=self.visual_transport.preparation_pending,
            performance_complete=self.attempt.performance_summary is not None),now)
        if self.run_pre_assessment_transition(now):
            return
        if (self.playback_session.running and self.visual_transport.grading_is_frozen(
                    now,grading_after=self.midi_ingress.resume_grading_after)):
            # The canonical recorder and live-assessment clock stand at the
            # paused source position. Do not inspect rolling checkpoints,
            # missed attacks, completion or recovery during the admitted
            # continuation's reading/count-in lead.
            return
        phrase = self.source_identity.plan.active_phrase
        score_beat = self.visual_transport.play_from_beat + max(
            0.0, self.transport_timing.elapsed_beat(now-self.visual_transport.run_at))

        step = self.attempt_progression.inspect(AttemptTick(
            phrase=phrase, boundaries=self.source_identity.plan.piece.bar_boundaries,
            now=now, score_beat=score_beat, from_beat=self.visual_transport.play_from_beat,
            run_at=self.visual_transport.run_at, next_boundary=self.visual_transport.next_boundary_beat,
            review_end=self.attempt.review_end_beat, preview=self.playback_session.preview_only,
            auto=self.playback_session.auto, mode=self.playback_session.mode,
            bpm=self.source_identity.plan.bpm, gap_beats=self.visual_transport.visual_gap_beats),
            self.recovery_workflows.assess_rolling_boundary, self.transport_timing.elapsed_seconds,
            exact_repeats=self.lesson_execution.flow_active())
        self.visual_transport.next_boundary_beat = step.next_boundary
        if step.action == "recovery":
            self.recovery_workflows.apply_rolling_recovery(
                step.recovery, phrase, step.grid, score_beat, now)
        elif step.action == "complete":
            self.complete_attempt(phrase, step.ending,
                                   phrase.sounding_end-phrase.start, step.duration, now)
            self.playback_session.refloor_fresh_announcement(TimedTakeSource(
                self.source_identity.plan.active_phrase,self.source_identity.plan.piece.bar_boundaries,
                self.source_identity.plan.piece.time_signatures,self.source_identity.plan.bpm,
                self.visual_transport.visual_gap_beats),
                physical_rest_enabled=self.visual_transport.short_rest is not None)


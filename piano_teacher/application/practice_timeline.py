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
    def __init__(self, *, lesson, notices, transport, take, transport_timing,
                          timed_playback, score, lesson_execution,
                          recovery_workflows, completion_continuations,
                          live_feedback_workflows, live_assessment,
                          measurement, policy_registry, library, midi_input,
                          listen, attempt_progression, read_models,
                          exposure_workflows, clock, poll_midi,
                          feedback_seconds):
        self.notices = notices
        self.lesson = lesson
        self.transport = transport
        self.take = take
        self.transport_timing, self.timed_playback = transport_timing, timed_playback
        self.score = score
        self.lesson_execution, self.recovery_workflows = lesson_execution, recovery_workflows
        self.completion_continuations = completion_continuations
        self.live_feedback_workflows, self.live_assessment = live_feedback_workflows, live_assessment
        self.measurement, self.policy_registry = measurement, policy_registry
        self.library = library
        self.listen = listen
        self.midi_input = midi_input
        self.attempt_progression = attempt_progression
        self.read_models, self.clock, self.poll_midi = read_models, clock, poll_midi
        self.exposure_workflows = exposure_workflows
        self.feedback_seconds = feedback_seconds

    def complete_attempt(self, phrase: Phrase, ending: float,
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
            performance_review=self.completion_continuations.performance_review,
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
        if not self.completion_continuations.apply_focused(
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
            self.completion_continuations.advance_pending_feedback(now,force_early=completion.force_early)
        elif completion.update_clock:
            self.take.finish_full_completion(publication)
            return True
        self.take.finish_full_completion(publication)
        return False

    def run_pre_assessment_transition(self, now: float) -> tuple[bool, bool]:
        """Apply a non-grading transition; return consumed and follow-up flags."""
        if self.transport.intent is not None:
            return True, False
        context = TransitionContext(
            has_plan=self.lesson.plan is not None,
            learning=self.transport.mode == "learn" and self.lesson.guided_controller is not None,
            paused=self.transport.paused, listening=self.transport.mode == "listen",
            preview_pending=self.transport.preview_loop_pending,
            preparation_pending=self.transport.preparation_pending,
            feedback_pending=self.take.feedback_pending,
            awaiting_score=self.transport.awaiting_score_revision is not None,
            rewind_pending=self.transport.pending_rewind is not None,
            running=self.transport.running, run_at=self.transport.run_at)
        decision = decide_transition(
            context, now=now, next_at=self.transport.next_at,
            preparation_at=self.transport.preparation_deadline)
        followup = False
        if decision.preparation_phase is not None:
            self.transport.enter_preparation_phase(decision.preparation_phase)
        if decision.action == "learning":
            self.lesson.advance_guided(connected=self.midi_input.connected, now=now)
            self.lesson_execution.save_guided_preparation()
        elif decision.action == "listening":
            if self.transport.running and self.listen.finished(now=now, run_at=self.transport.run_at):
                self.transport.finish_take()
                self.notices.feedback = "Example complete"
                self.notices.next_action = (
                    "Choose Learn to find the notes, or Practice to play the rhythm.")
                if (self.lesson_execution.flow_active() and self.lesson.flow_state is not None
                        and self.lesson.flow_state.step is practice_flow.Step.LISTEN):
                    self.lesson_execution.flow_execute(self.lesson.flow_listen_finished())
        elif decision.action == "preview_due":
            deadline = self.transport.next_at
            self.transport.advance_source_stride(self.score.source_model()[
                "practice_timeline"]["stride_beats"])
            self.timed_playback.continue_at(SCHEDULER.continuation(
                    self.transport_timing.collect_continuation_measurement(deadline, 0.0),
                    now=self.clock(),bpm=self.transport_timing.presentation_bpm()))
        elif decision.action == "feedback":
            publication = self.take.pending_full_completion
            if publication is not None:
                followup = self.finish_full_passage(publication.result,
                    publication.total_beats,publication.duration,now)
            else:
                self.completion_continuations.advance_pending_feedback(now)
        elif decision.action == "rewind_due":
            if self.take.guided_recovery_pending:
                self.lesson_execution.begin_learn(from_beat=self.transport.pending_rewind, recovery=True,
                    exposure=self.take.pending.decision.next_exposure)
            else:
                target = self.transport.pending_rewind
                self.timed_playback.continue_at(
                    SCHEDULER.continuation(
                    self.transport_timing.collect_continuation_measurement(self.transport.next_at, target),
                    now=self.clock(),bpm=self.transport_timing.presentation_bpm()),
                    from_beat=target)
        return decision.consumed, followup

    def publish_failed_transition(self) -> None:
        """Make a faulted tick visibly paused without replaying any effects.

        The failed event can have already stopped grading or installed an
        idempotent recovery effect. Never rerun it merely to bring the
        physical authorization ledger into agreement with the paused clock.
        """
        self.transport.advance(self.transport_timing.playback_facts())

    def publish_settled(self) -> None:
        """Publish one accepted outcome after transitions and deferred MIDI.

        Replaying deferred hardware events before this publication makes
        controls, live feedback and transport describe the same final source.
        """
        self.transport.advance(self.transport_timing.playback_facts())
        self.read_models.prepare_score_presentation()
        try:
            self.live_feedback_workflows.publish_live()
        except Exception:
            logging.getLogger(__name__).exception(
                "Live assessment publication failed; skipping this tick")

    def update_transition(self) -> bool:
        """Advance the backend clock under its existing session lock."""
        self.poll_midi()
        self.midi_input.advance_calibration(self.clock())
        self.exposure_workflows.apply_listen_failure()
        now = self.clock()
        learning = self.transport.mode == "learn"
        guided_completed = bool(
            learning and self.lesson.guided_controller is not None
            and self.lesson.guided_controller.snapshot(now=now)["completed"])
        self.measurement.observe_phase(CapturePhaseFacts(
            paused=self.transport.paused,learning=learning,
            awaiting_score=self.transport.awaiting_score_revision is not None,
            guided_completed=guided_completed,running=self.transport.running,
            count_in_activation=max(
                self.transport.run_at,
                self.midi_input.resume_grading_after),
            mode=self.transport.mode,preview=self.transport.preview_only,
            pending_result=self.take.pending_result is not None,
            preparation_pending=self.transport.preparation_pending,
            performance_complete=self.take.performance_summary is not None),now)
        # A rolling boundary is admitted once. A failed presentation must
        # replay the original receipt before any rewind/next-boundary branch
        # can consume this tick. Still honor physical score admission: it may
        # already be awaiting an external attestation and must not be
        # disturbed by a duplicate transport effect.
        rolling = self.take.rolling_record
        if (rolling is not None and rolling.transition is not None
                and self.transport.mode == "practice"
                and self.transport.running
                and not self.transport.paused
                and self.transport.intent is None):
            self.recovery_workflows.apply_rolling_recovery(
                rolling.decision, rolling.phrase, rolling.grid,
                rolling.score_beat, now)
            return False
        consumed, followup = self.run_pre_assessment_transition(now)
        if consumed or followup:
            return followup
        if (self.transport.running and self.transport.grading_is_frozen(
                    now,grading_after=self.midi_input.resume_grading_after)):
            # The canonical recorder and live-assessment clock stand at the
            # paused source position. Do not inspect rolling checkpoints,
            # missed attacks, completion or recovery during the admitted
            # continuation's reading/count-in lead.
            return False
        phrase = self.lesson.plan.active_phrase
        score_beat = self.transport.play_from_beat + max(
            0.0, self.transport_timing.elapsed_beat(now-self.transport.run_at))

        step = self.attempt_progression.inspect(AttemptTick(
            phrase=phrase, boundaries=self.lesson.plan.piece.bar_boundaries,
            now=now, score_beat=score_beat, from_beat=self.transport.play_from_beat,
            run_at=self.transport.run_at, next_boundary=self.transport.next_boundary_beat,
            review_end=self.take.review_end_beat, preview=self.transport.preview_only,
            auto=self.transport.auto, mode=self.transport.mode,
            bpm=self.lesson.plan.bpm, gap_beats=self.transport.visual_gap_beats),
            self.recovery_workflows.assess_rolling_boundary, self.transport_timing.elapsed_seconds,
            exact_repeats=self.lesson_execution.flow_active())
        self.transport.advance_boundary(step.next_boundary)
        followup = False
        if step.action == "recovery":
            self.recovery_workflows.apply_rolling_recovery(
                step.recovery, phrase, step.grid, score_beat, now)
        elif step.action == "complete":
            followup = self.complete_attempt(phrase, step.ending,
                phrase.sounding_end-phrase.start, step.duration, now)
            self.transport.refloor_fresh_announcement(TimedTakeSource(
                self.lesson.plan.active_phrase,self.lesson.plan.piece.bar_boundaries,
                self.lesson.plan.piece.time_signatures,self.lesson.plan.bpm,
                self.transport.visual_gap_beats),
                physical_rest_enabled=self.transport.short_rest is not None)
        return followup


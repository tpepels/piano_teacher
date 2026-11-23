"""Timed playback in three owners: start, continuation, pause/resume.

TimedStart opens the one take a physical receipt authorized; the approved
lesson and source identity are consumed, never reselected.
PlaybackContinuation requests the next admission at a deadline.
PauseResume freezes and resumes the timeline and Free, and starts Listen
once its score and audio are ready.
"""
from __future__ import annotations
from .playback_facts import TimedTakeSource, TimedStartRequest, ResumeRequest, RestResumeFacts
from .musical_scheduler import SCHEDULER


class TimedStart:
    def __init__(self, *, lesson, notices, transport, take, exposure_workflows,
                 midi_input, score, evidence_context, transport_timing, lock):
        self.lesson = lesson
        self.notices = notices
        self.transport = transport
        self.take = take
        self.exposure_workflows = exposure_workflows
        self.midi_input = midi_input
        self.score = score
        self.evidence_context = evidence_context
        self.transport_timing = transport_timing
        self.lock = lock

    def start(self, *, from_beat: float | None = None, mode: str = "practice",
              loop_continuation: bool = False, scheduled_deadline: float,
              count_in_plan, effect=None, reason="transition"):
        """Open the one take the coordinator's physical receipt authorized."""
        with self.lock:
            self.transport.require_authorized_start()
            if self.lesson.plan is None:
                raise ValueError("Open a piece first")
            selected = None
            pending = self.take.pending
            if loop_continuation and pending is not None and pending.receipt is not None:
                selected = pending.decision.next_exposure
            if effect is not None:
                selected = effect.decision.next_exposure
                if selected is None:
                    return
                self.lesson.install_command(effect)
            if selected is not None and selected.stage_key == self.lesson.plan.identity:
                from_beat,mode = selected.from_beat,selected.mode
            if self.transport.mode == "learn":
                self.exposure_workflows.prepare_practice(exposure=selected,reason=reason)
                return
            self.lesson.clear_guided_selection()
            self.lesson.discard_guided_return()
            p = self.lesson.plan
            started = self.transport.begin_timed(
                TimedTakeSource(p.active_phrase,p.piece.bar_boundaries,
                    p.piece.time_signatures,p.bpm,
                    self.score.source_model()["practice_timeline"]["gap"]["duration_beats"]),
                TimedStartRequest(mode=mode,
                    position=self.lesson.opening_beat if from_beat is None else from_beat,
                    automatic=selected.automatic if selected is not None else mode == "practice",
                    connected=self.midi_input.connected,loop_continuation=loop_continuation,
                    scheduled_deadline=scheduled_deadline,
                    presentation_lead_seconds=0.0,
                    count_in_plan=count_in_plan))
            self.transport.advance_boundary(started.next_boundary_beat)
            try:
                self.transport.capture_start(self.evidence_context.build(
                    scope=started.scope,start=started.from_beat,end=started.end_beat,
                    run_at=started.run_at,tempo_map=self.transport_timing.active_tempo_map()))
            except Exception:
                self.notices.feedback = "Could not record the start of this attempt"
                raise
            self.notices.feedback = "Count in, then play"
            self.notices.next_action = started.next_action


class PlaybackContinuation:
    def __init__(self, *, lesson, transport, transport_timing, score,
                 notices, clock):
        self.lesson = lesson
        self.transport = transport
        self.transport_timing = transport_timing
        self.score = score
        self.notices = notices
        self.clock = clock

    def continue_at(self, deadline: float, *, from_beat: float = 0.0):
        """Continue only through the unified score-admission gate."""
        # Check the canonical terminal admission latch BEFORE changing
        # visual-transport or preparation state. Repeated automatic
        # callbacks after exhaustion must leave a visible FAILED
        # transaction, not silently clear the old rest schedule and
        # replace the failure with "Preparing the next passage".
        if self.transport.automatic_request_blocked(
                self.transport_timing.playback_facts(from_beat=from_beat),
                action="auto", mode=self.transport.mode,
                from_beat=from_beat):
            return
        self.transport.prepare_admitted_continuation()
        self.transport_timing.request_playback(
            action="auto", mode=self.transport.mode,
            from_beat=from_beat, earliest_deadline=deadline,
            fixed_deadline=deadline if self.lesson.flow_active else None)
        self.transport.clear_scheduled_start()
        self.notices.feedback = "Preparing the next passage"

    def continue_measured(self, deadline: float, *, from_beat: float = 0.0):
        """Continue from `from_beat` at the scheduler's measured continuation."""
        self.continue_at(SCHEDULER.continuation(
            self.transport_timing.collect_continuation_measurement(deadline, from_beat),
            now=self.clock(), bpm=self.transport_timing.presentation_bpm()),
            from_beat=from_beat)

class PauseResume:
    def __init__(self, *, lesson, transport, transport_timing, midi_input,
                 listen_outcomes, notices, phase, clock):
        self.lesson = lesson
        self.transport = transport
        self.transport_timing = transport_timing
        self.midi_input = midi_input
        self.listen_outcomes = listen_outcomes
        self.notices = notices
        self.phase = phase
        self.clock = clock

    def begin_listen_if_ready(self):
        self.listen_outcomes.apply_failure()
        activation = self.transport.begin_listen_if_ready(
            revision=self.lesson.revision)
        if activation.requested_count_in is not None:
            self.transport_timing.request_playback(action="listen",mode="listen",from_beat=activation.from_beat,
                count_in_beats=activation.requested_count_in)

    def pause(self, *, pending_admission: bool = False):
        now = self.clock()
        context = ("admitting" if pending_admission else self.phase(now)) \
            if not self.transport.paused else ""
        self.transport.pause(context=context,now=now)
        if self.transport.mode == "learn" and self.lesson.guided_controller is not None:
            self.lesson.guided_controller.pause(now=now)

    def resume(self, *, presentation_lead_seconds: float = 0.0,
               scheduled_deadline: float | None = None):
        resumed = self.transport.resume_timeline(ResumeRequest(
            learning=self.transport.mode == "learn" and self.lesson.guided_controller is not None,
            bpm=self.lesson.plan.bpm if self.lesson.plan is not None else None,
            full_count_in_beats=self.transport_timing.next_count_in_beats(),
            midi_connected=self.midi_input.connected,reading_lead_seconds=presentation_lead_seconds,
            scheduled_deadline=scheduled_deadline))
        if resumed.learning:
            self.lesson.guided_controller.resume(now=resumed.now)
        announced = self.transport.announced_continuation
        self.transport.reannounce_after_rest_pause(RestResumeFacts(
            now=resumed.now,reading_lead_seconds=presentation_lead_seconds,
            running=self.transport.running,mode=self.transport.mode,
            bpm=self.lesson.plan.bpm if self.lesson.plan is not None else None,
            presentation_bpm=self.transport_timing.presentation_bpm(),horizon_beats=self.transport.continuous_horizon_beats,
            physical_rest_enabled=self.transport.short_rest is not None,
            rest=(self.transport_timing.collect_rest_measurement(from_beat=announced[0],source_end=0.0)
                if announced is not None else None)))
        completion = self.transport.finish_resume(resumed)
        self.notices.clear_fault()
        if completion.feedback is not None:
            self.notices.feedback = completion.feedback
        return completion

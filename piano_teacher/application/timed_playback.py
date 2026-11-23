"""Apply authorized timed take starts, Listen readiness and transport pauses.

All timed starts require PlaybackCoordinator's physical receipt in desktop
mode. The approved lesson and source identity are consumed, never reselected.
"""
from __future__ import annotations
from .playback_facts import TimedTakeSource, TimedStartRequest, ResumeRequest, RestResumeFacts


class TimedPlayback:
    def __init__(self, *, source_identity, lesson_cursor, notices,
                 playback_session, playback, attempt_settlement,
                 teaching_decisions, exposure_workflows, guided_session,
                 visual_transport, midi, score_read, evidence_context,
                 transport_timing, lesson_execution, clock, lock, phase):
        self.source_identity, self.lesson_cursor = source_identity, lesson_cursor
        self.notices, self.playback_session = notices, playback_session
        self.playback, self.attempt_settlement = playback, attempt_settlement
        self.teaching_decisions = teaching_decisions
        self.exposure_workflows, self.guided_session = exposure_workflows, guided_session
        self.visual_transport, self.midi = visual_transport, midi
        self.score_read, self.evidence_context = score_read, evidence_context
        self.transport_timing, self.lesson_execution = transport_timing, lesson_execution
        self.clock, self.lock, self.phase = clock, lock, phase

    def start(self, *, from_beat: float | None = None, mode: str = "practice",
              loop_continuation: bool = False, scheduled_deadline: float,
              count_in_plan, effect=None, reason="transition"):
        """Open the one take the coordinator's physical receipt authorized."""
        with self.lock:
            self.playback_session.require_authorized_start()
            if self.source_identity.plan is None:
                raise ValueError("Open a piece first")
            selected = None
            pending = self.attempt_settlement.pending
            if loop_continuation and pending is not None and pending.receipt is not None:
                selected = pending.decision.next_exposure
            if effect is not None:
                selected = effect.decision.next_exposure
                if selected is None:
                    return
                self.teaching_decisions.install_command(effect)
            if selected is not None and selected.stage_key == self.source_identity.plan.identity:
                from_beat,mode = selected.from_beat,selected.mode
            if self.playback_session.mode == "learn":
                self.exposure_workflows.prepare_practice(exposure=selected,reason=reason)
                return
            self.guided_session.clear_selection()
            self.guided_session.discard_return()
            p = self.source_identity.plan
            started = self.playback_session.begin_timed(
                TimedTakeSource(p.active_phrase,p.piece.bar_boundaries,
                    p.piece.time_signatures,p.bpm,
                    self.score_read.source_model()["practice_timeline"]["gap"]["duration_beats"]),
                TimedStartRequest(mode=mode,
                    position=self.lesson_cursor.opening_beat if from_beat is None else from_beat,
                    automatic=selected.automatic if selected is not None else mode == "practice",
                    connected=self.midi.connected,loop_continuation=loop_continuation,
                    scheduled_deadline=scheduled_deadline,
                    presentation_lead_seconds=0.0,
                    count_in_plan=count_in_plan))
            self.visual_transport.advance_boundary(started.next_boundary_beat)
            try:
                self.playback_session.capture_start(self.evidence_context.build(
                    scope=started.scope,start=started.from_beat,end=started.end_beat,
                    run_at=started.run_at,tempo_map=self.transport_timing.active_tempo_map()))
            except Exception:
                self.notices.feedback = "Could not record the start of this attempt"
                raise
            self.notices.feedback = "Count in, then play"
            self.notices.next_action = started.next_action

    def continue_at(self, deadline: float, *, from_beat: float = 0.0):
        """Continue only through the unified score-admission gate."""
        # Check the canonical terminal admission latch BEFORE changing
        # visual-transport or preparation state. Repeated automatic
        # callbacks after exhaustion must leave a visible FAILED
        # transaction, not silently clear the old rest schedule and
        # replace the failure with "Preparing the next passage".
        if self.playback.automatic_request_blocked(
                self.transport_timing.playback_facts(from_beat=from_beat),
                action="auto", mode=self.playback_session.mode,
                from_beat=from_beat):
            return
        self.playback_session.prepare_admitted_continuation()
        self.transport_timing.request_playback(
            action="auto", mode=self.playback_session.mode,
            from_beat=from_beat, earliest_deadline=deadline,
            fixed_deadline=deadline if self.lesson_execution.flow_active() else None)
        self.visual_transport.clear_scheduled_start()
        self.notices.feedback = "Preparing the next passage"

    def begin_listen_if_ready(self):
        self.exposure_workflows.apply_listen_failure()
        activation = self.playback_session.begin_listen_if_ready(
            revision=self.source_identity.revision)
        if activation.requested_count_in is not None:
            self.transport_timing.request_playback(action="listen",mode="listen",from_beat=activation.from_beat,
                count_in_beats=activation.requested_count_in)

    def pause(self, *, pending_admission: bool = False):
        now = self.clock()
        context = ("admitting" if pending_admission else self.phase(now)) \
            if not self.visual_transport.paused else ""
        self.playback_session.pause(context=context,now=now)
        if self.playback_session.mode == "learn" and self.guided_session.controller is not None:
            self.guided_session.controller.pause(now=now)

    def resume(self, *, presentation_lead_seconds: float = 0.0,
               scheduled_deadline: float | None = None):
        resumed = self.playback_session.resume_timeline(ResumeRequest(
            learning=self.playback_session.mode == "learn" and self.guided_session.controller is not None,
            bpm=self.source_identity.plan.bpm if self.source_identity.plan is not None else None,
            full_count_in_beats=self.transport_timing.next_count_in_beats(),
            midi_connected=self.midi.connected,reading_lead_seconds=presentation_lead_seconds,
            scheduled_deadline=scheduled_deadline))
        if resumed.learning:
            self.guided_session.controller.resume(now=resumed.now)
        announced = self.visual_transport.announced_continuation
        self.visual_transport.reannounce_after_rest_pause(RestResumeFacts(
            now=resumed.now,reading_lead_seconds=presentation_lead_seconds,
            running=self.playback_session.running,mode=self.playback_session.mode,
            bpm=self.source_identity.plan.bpm if self.source_identity.plan is not None else None,
            presentation_bpm=self.transport_timing.presentation_bpm(),horizon_beats=self.visual_transport.continuous_horizon_beats,
            physical_rest_enabled=self.visual_transport.short_rest is not None,
            rest=(self.transport_timing.collect_rest_measurement(from_beat=announced[0],source_end=0.0)
                if announced is not None else None)))
        completion = self.playback_session.finish_resume(resumed)
        if completion.feedback is not None:
            self.notices.feedback = completion.feedback
        return completion


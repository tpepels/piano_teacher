"""Projection of the one current playback/learning phase.

The projection consumes immutable observations and has no transition side
effects. There is no additional musical clock or teaching policy.
"""
from __future__ import annotations
from ..state_projection import PhaseSnapshot, project_phase


class SessionPhase:
    def __init__(self, *, transport, guided_session,
                 midi_ingress, attempt, attempt_settlement):
        self.transport = transport
        self.guided_session = guided_session
        self.midi_ingress = midi_ingress
        self.attempt = attempt
        self.attempt_settlement = attempt_settlement

    def at(self, now: float) -> str:
        teaching_phase = None
        if not self.transport.paused and self.transport.mode == "learn" and self.guided_session.controller is not None:
            teaching_phase = ("loading" if self.transport.awaiting_score_revision is not None
                              else self.guided_session.controller.snapshot(now=now)["phase"])
        if (self.transport.running and not self.transport.paused
                and now < self.midi_ingress.resume_grading_after):
            return "count_in"
        return project_phase(PhaseSnapshot(
            paused=self.transport.paused, running=self.transport.running, run_at=self.transport.run_at,
            teaching_phase=teaching_phase,
            performance_complete=self.attempt.performance_summary is not None,
            preview_loop_pending=self.transport.preview_loop_pending,
            review_complete=self.attempt.review_session_complete,
            pending_result=self.attempt_settlement.pending_result is not None,
            awaiting_score=self.transport.awaiting_score_revision is not None,
            pending_rewind=self.transport.pending_rewind is not None,
        ), mode=self.transport.mode, now=now)


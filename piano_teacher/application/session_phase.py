"""Projection of the one current playback/learning phase.

The projection consumes immutable observations and has no transition side
effects. There is no additional musical clock or teaching policy.
"""
from __future__ import annotations
from ..state_projection import PhaseSnapshot, project_phase


class SessionPhase:
    def __init__(self, *, transport, lesson, midi_input, take):
        self.transport = transport
        self.lesson = lesson
        self.midi_input = midi_input
        self.take = take


    def at(self, now: float) -> str:
        teaching_phase = None
        if not self.transport.paused and self.transport.mode == "learn" and self.lesson.guided_controller is not None:
            teaching_phase = ("loading" if self.transport.awaiting_score_revision is not None
                              else self.lesson.guided_controller.snapshot(now=now)["phase"])
        if (self.transport.running and not self.transport.paused
                and now < self.midi_input.resume_grading_after):
            return "count_in"
        return project_phase(PhaseSnapshot(
            paused=self.transport.paused, running=self.transport.running, run_at=self.transport.run_at,
            teaching_phase=teaching_phase,
            performance_complete=self.take.performance_summary is not None,
            preview_loop_pending=self.transport.preview_loop_pending,
            review_complete=self.take.review_session_complete,
            pending_result=self.take.pending_result is not None,
            awaiting_score=self.transport.awaiting_score_revision is not None,
            pending_rewind=self.transport.pending_rewind is not None,
        ), mode=self.transport.mode, now=now)


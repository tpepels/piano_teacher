"""Non-grading tick transitions: Free, Listen end, preview, feedback, rewind.

The decision itself is the pure `decide_transition`; this class applies
the chosen transition through its owner.
"""
from __future__ import annotations
from .practice_transitions import TransitionContext, decide_transition
from . import practice_flow


class PreAssessmentTransitions:
    def __init__(self, *, lesson, transport, take, midi_input,
                 lesson_execution, listen_outcomes, timed_playback,
                 settlement):
        self.lesson = lesson
        self.transport = transport
        self.take = take
        self.midi_input = midi_input
        self.lesson_execution = lesson_execution
        self.listen_outcomes = listen_outcomes
        self.timed_playback = timed_playback
        self.settlement = settlement

    def run(self, now: float) -> tuple[bool, bool]:
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
            if self.listen_outcomes.finish(now):
                if (self.lesson_execution.flow_active() and self.lesson.flow_state is not None
                        and self.lesson.flow_state.step is practice_flow.Step.LISTEN):
                    self.lesson_execution.flow_execute(self.lesson.flow_listen_finished())
        elif decision.action == "preview_due":
            self.timed_playback.continue_preview()
        elif decision.action == "feedback":
            followup = self.settlement.feedback_due(now)
        elif decision.action == "rewind_due":
            if self.take.guided_recovery_pending:
                self.lesson_execution.begin_learn(from_beat=self.transport.pending_rewind, recovery=True,
                    exposure=self.take.pending.decision.next_exposure)
            else:
                self.timed_playback.continue_measured(
                    self.transport.next_at, from_beat=self.transport.pending_rewind)
        return decision.consumed, followup

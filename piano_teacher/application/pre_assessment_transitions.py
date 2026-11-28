"""Non-grading tick transitions: Free, Listen end, feedback, rewind.

The decision itself is the pure `decide_transition`; this class applies
the chosen transition through its owner.
"""
from __future__ import annotations
from .practice_transitions import TransitionContext, decide_transition
from . import practice_flow


class PreAssessmentTransitions:
    def __init__(self, *, lesson, transport, take, midi_input,
                 course, listen_outcomes, continuation,
                 settlement):
        self.lesson = lesson
        self.transport = transport
        self.take = take
        self.midi_input = midi_input
        self.course = course
        self.listen_outcomes = listen_outcomes
        self.continuation = continuation
        self.settlement = settlement

    def run(self, now: float) -> tuple[bool, bool]:
        """Apply a non-grading transition; return consumed and follow-up flags."""
        if (self.transport.intent is not None or
                (self.transport.running and not self.transport.presentation_confirmed)):
            # No empty take, checkpoint, Listen completion or successor
            # may settle while the renderer has not attested its ink.
            return True, False
        context = TransitionContext(
            has_plan=self.lesson.plan is not None,
            learning=self.transport.mode == "learn" and self.lesson.guided_controller is not None,
            paused=self.transport.paused, listening=self.transport.mode == "listen",
            feedback_pending=self.take.feedback_pending,
            awaiting_score=self.transport.awaiting_score_revision is not None,
            rewind_pending=self.transport.pending_rewind is not None,
            running=self.transport.running, run_at=self.transport.run_at)
        decision = decide_transition(
            context, now=now)
        followup = False
        if decision.action == "learning":
            self.lesson.advance_guided(connected=self.midi_input.connected, now=now)
            self.course.save_guided_preparation()
        elif decision.action == "listening":
            if self.listen_outcomes.finish(now):
                if (self.lesson.flow_state is not None
                        and self.lesson.flow_state.step is practice_flow.Step.LISTEN):
                    self.course.flow_execute(self.lesson.flow_listen_finished())
        elif decision.action == "feedback":
            followup = self.settlement.feedback_due(now)
        elif decision.action == "rewind_due":
            if self.take.guided_recovery_pending:
                self.course.begin_learn(from_beat=self.transport.pending_rewind, recovery=True,
                    exposure=self.take.pending.decision.next_exposure)
            else:
                self.continuation.continue_at(from_beat=self.transport.pending_rewind)
        return decision.consumed, followup

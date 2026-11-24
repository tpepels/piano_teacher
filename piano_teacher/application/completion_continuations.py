"""Everything that happens immediately after a take ends.

A graded take is assessed by TakeGrading and
its immediately settled consequence (policy response, performance,
section or partial-recovery review, selected exposure) is applied here.
A full passage is handed to SettlementContinuation, which settles it at
its durable successor boundary.
"""
from __future__ import annotations
from ..music import Phrase
from .passage_outcome_presenter import performance_next_action


class TakeCompletion:
    def __init__(self, *, lesson, notices, take, transport, transport_timing,
                 continuation, course,
                 grading, settlement):
        self.lesson = lesson
        self.notices = notices
        self.take = take
        self.transport = transport
        self.transport_timing = transport_timing
        self.continuation = continuation
        self.course = course
        self.grading = grading
        self.settlement = settlement

    def complete_take(self, phrase: Phrase, ending: float,
                          total_beats: float, duration: float, now: float) -> bool:
        """Apply post-performance state after the score's settlement interval.

        Called from PracticeSession's locked event drain. Assessment
        and grading occur only after a completed take.
        Returns whether another same-tick transition must be queued.
        """
        completed = self.grading.grade(phrase, ending, now)
        result = completed.assessed.result
        self.notices.feedback = completed.assessed.feedback
        if not self.apply_focused(
                completed.effect, phrase=phrase, result=result, now=now):
            return self.settlement.finish_full_passage(result,total_beats,duration,now)
        return False

    def apply_focused(self, effect, *, phrase, result, now: float) -> bool:
        """Apply one immediately settled focused/performance consequence.

        Returns False for a full passage, whose consequence is applied by
        dispatch_effect only after its durable successor boundary.
        """
        if effect.action == "perform":
            self.finish_performance_review(phrase,result)
        elif effect.action == "exposure":
            self.course.enter_selected_exposure(effect.exposure)
        elif effect.action == "full_passage":
            return False
        else:
            raise ValueError(f"Unknown completion consequence {effect.action!r}")
        return True


    def finish_performance_review(self, phrase: Phrase, result):
        """Publish review only after its evidence and source feedback commit."""
        self.notices.next_action = performance_next_action(
            summary=self.take.performance_summary)
        self.transport.stop_automatic()


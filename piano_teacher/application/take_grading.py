"""Grade one completed take and publish its settled marks.

Owns the grading inputs (recorder, tempo map, grading and mistake
policies, performance review) and the publication of the take's final
marks. It does not choose what happens next; TakeCompletion does.
"""
from __future__ import annotations

from ..music import Phrase


class TakeGrading:
    def __init__(self, *, lesson, take, transport, transport_timing, score,
                 policy_registry, assessment, live_feedback_workflows,
                 measurement):
        self.lesson = lesson
        self.take = take
        self.transport = transport
        self.transport_timing = transport_timing
        self.score = score
        self.policy_registry = policy_registry
        self.assessment = assessment
        self.live_feedback_workflows = live_feedback_workflows
        self.measurement = measurement

    @property
    def policies(self):
        """The configured grading policies (one per tempo map)."""
        return self.policy_registry.grading

    def grade(self, phrase: Phrase, ending: float, now: float):
        """Assess the take, publish its final marks, end it; return the result."""
        completed = self.take.complete_take(
            phrase=phrase,hand=self.lesson.plan.hand,bpm=self.lesson.plan.bpm,
            played=(self.take.recorder.presses
                    if self.take.recorder else ()),
            from_beat=self.transport.play_from_beat,end_beat=ending,
            tempo=self.transport_timing.graded_tempo_map(),policies=self.policy_registry.grading,
            layout_for_feedback=self.score.completed_take_layout,
            mode=self.transport.mode,
            performance_review=self.performance_review,
            prepare_decision=self.lesson.prepare_decision,
            plan=self.lesson.plan,binding=self.lesson.decision_binding(),now=now,
            score_revision=self.lesson.revision)
        assessed = completed.assessed
        verdict = completed.pending.decision.verdict
        ignored = bool(verdict and verdict.ignored)
        if ignored:
            # Preserve the internal assessment identity for the ordinary
            # settlement/continuation, without publishing a failed review.
            from dataclasses import replace
            assessed = replace(assessed,marks=[],unmapped=0,feedback="Same tempo")
            completed = replace(completed,assessed=assessed)
        self.take.publish_completion(
            marks=assessed.marks,unmapped=assessed.unmapped)
        # The completed take's settled grades, before any transition can
        # start another transport.
        self.live_feedback_workflows.publish_final(self.take.feedback_marks)
        self.transport.finish_take()
        self.take.finish_review(None if ignored else completed.summary,self.lesson.plan.identity)
        self.measurement.phase_changed("feedback", now)
        return completed

    def performance_review(self, phrase: Phrase, result) -> dict:
        """Retained engine API; assessment service owns report construction."""
        tempo = self.transport_timing.graded_tempo_map()
        elapsed_to_beat = (None if tempo is None else
            lambda seconds: tempo.beat_at(tempo.seconds_at(self.transport.play_from_beat)+seconds))
        return self.assessment.review(
            phrase, result, bar_boundaries=self.lesson.plan.piece.bar_boundaries,
            played_from_beat=self.transport.play_from_beat, bpm=self.lesson.plan.bpm,
            elapsed_to_beat=elapsed_to_beat)

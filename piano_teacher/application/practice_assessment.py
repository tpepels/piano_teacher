"""Injectable practice grading policies, independent of transport and mastery.

Both implementations use practice.evaluate, the same per-note tolerances,
and the original source note identities. Selection occurs once at the API
boundary; PracticeEngine does not branch on stage names or scoring clocks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from ..assessment_service import AssessmentService
from ..exercise_contracts import TempoMap
from ..feedback import project_assessment
from ..measure_grid import chunk_start_at_end, phrase_grid
from ..music import Phrase
from ..practice import Assessment, PlayedNote, evaluate
from ..recovery import RecoveryDecision, check_rolling_two_bar_window, check_two_bar_window
from ..timed_assessment import assess_timed_window, timed_live_marks, timed_rolling_recovery


class PracticeTimingPolicy(Protocol):
    def grade(self, phrase: Phrase, *, hand: str, bpm: float,
              played: Sequence[PlayedNote], from_beat: float,
              end_beat: float, tempo: TempoMap | None) -> Assessment: ...

    def live(self, phrase: Phrase, *, hand: str, bpm: float,
             played: Sequence[PlayedNote], from_beat: float,
             elapsed_seconds: float, bar_boundaries: Sequence[float],
             layout: dict, tempo: TempoMap | None) -> list[dict]: ...

    def recover(self, phrase: Phrase, *, hand: str, bpm: float,
                played: Sequence[PlayedNote], from_beat: float,
                end_beat: float, grid: tuple[float, ...],
                threshold: int, warmup: bool, tempo: TempoMap | None
                ) -> RecoveryDecision | None: ...


@dataclass(frozen=True)
class FixedTimingPolicy:
    assessment: AssessmentService

    def grade(self, phrase, *, hand, bpm, played, from_beat, end_beat, tempo):
        return self.assessment.assess_take(
            phrase, hand=hand, bpm=bpm, played=list(played),
            from_beat=from_beat, end_beat=end_beat, evaluator=evaluate)

    def live(self, phrase, *, hand, bpm, played, from_beat,
             elapsed_seconds, bar_boundaries, layout, tempo):
        return self.assessment.live_marks(
            phrase=phrase, hand=hand, bpm=bpm, played=list(played),
            played_from_beat=from_beat, elapsed_seconds=elapsed_seconds,
            bar_boundaries=bar_boundaries, layout=layout,
            projector=project_assessment)

    def recover(self, phrase, *, hand, bpm, played, from_beat,
                end_beat, grid, threshold, warmup, tempo):
        if warmup:
            return check_two_bar_window(
                phrase, hand, bpm, list(played), from_beat=from_beat,
                end_beat=end_beat, beats_per_bar=grid[1]-grid[0],
                threshold=threshold,
                window_start_beat=chunk_start_at_end(grid, end_beat))
        return check_rolling_two_bar_window(
            phrase, hand, bpm, list(played), from_beat=from_beat,
            end_beat=end_beat, grid=grid, threshold=threshold)


@dataclass(frozen=True)
class MappedTimingPolicy:
    def _require(self, tempo: TempoMap | None) -> TempoMap:
        if tempo is None:
            raise ValueError("Mapped timing requires a tempo map")
        return tempo

    def grade(self, phrase, *, hand, bpm, played, from_beat, end_beat, tempo):
        return assess_timed_window(
            phrase, hand, self._require(tempo), played,
            from_beat=from_beat, end_beat=end_beat)

    def live(self, phrase, *, hand, bpm, played, from_beat,
             elapsed_seconds, bar_boundaries, layout, tempo):
        return timed_live_marks(
            phrase, hand, self._require(tempo), played, from_beat=from_beat,
            elapsed_seconds=elapsed_seconds,
            grid=phrase_grid(phrase, bar_boundaries), layout=layout)

    def recover(self, phrase, *, hand, bpm, played, from_beat,
                end_beat, grid, threshold, warmup, tempo):
        return timed_rolling_recovery(
            phrase, hand, self._require(tempo), played, from_beat=from_beat,
            end_beat=end_beat, grid=grid, threshold=threshold)


@dataclass(frozen=True)
class PracticeAssessmentPolicies:
    """Injection point for the fixed and shaped timing implementations."""
    fixed: PracticeTimingPolicy
    mapped: PracticeTimingPolicy

    @classmethod
    def defaults(cls, assessment: AssessmentService) -> "PracticeAssessmentPolicies":
        return cls(FixedTimingPolicy(assessment), MappedTimingPolicy())

    def select(self, tempo: TempoMap | None) -> PracticeTimingPolicy:
        return self.fixed if tempo is None else self.mapped

    @staticmethod
    def project(result: Assessment, phrase: Phrase, *, bpm: float,
                layout: dict, from_beat: float, tempo: TempoMap | None) -> dict:
        elapsed_to_beat = None
        if tempo is not None:
            offset = tempo.seconds_at(from_beat)
            elapsed_to_beat = lambda seconds: tempo.beat_at(offset + seconds)
        return project_assessment(
            result, phrase, bpm, layout, played_from_beat=from_beat,
            elapsed_to_beat=elapsed_to_beat)

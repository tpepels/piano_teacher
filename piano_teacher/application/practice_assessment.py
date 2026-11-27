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
from ..music import Phrase
from ..practice import Assessment, PlayedNote, evaluate
from ..timed_assessment import assess_timed_window, timed_live_marks


class PracticeTimingPolicy(Protocol):
    def grade(self, phrase: Phrase, *, hand: str, bpm: float,
              played: Sequence[PlayedNote], from_beat: float,
              end_beat: float, tempo: TempoMap | None) -> Assessment: ...

    def live(self, phrase: Phrase, *, hand: str, bpm: float,
             played: Sequence[PlayedNote], from_beat: float,
             elapsed_seconds: float, tempo: TempoMap | None) -> list[dict]: ...



@dataclass(frozen=True)
class FixedTimingPolicy:
    assessment: AssessmentService
    grade_note_holds: bool = False

    def grade(self, phrase, *, hand, bpm, played, from_beat, end_beat, tempo):
        return self.assessment.assess_take(
            phrase, hand=hand, bpm=bpm, played=list(played),
            from_beat=from_beat, end_beat=end_beat,
            evaluator=lambda source, hand, bpm, events: evaluate(
                source, hand, bpm, events, grade_note_holds=self.grade_note_holds))

    def live(self, phrase, *, hand, bpm, played, from_beat,
             elapsed_seconds, tempo):
        return self.assessment.live_marks(
            phrase=phrase, hand=hand, bpm=bpm, played=list(played),
            played_from_beat=from_beat, elapsed_seconds=elapsed_seconds,
            grade_note_holds=self.grade_note_holds)



@dataclass(frozen=True)
class MappedTimingPolicy:
    grade_note_holds: bool = False

    def _require(self, tempo: TempoMap | None) -> TempoMap:
        if tempo is None:
            raise ValueError("Mapped timing requires a tempo map")
        return tempo

    def grade(self, phrase, *, hand, bpm, played, from_beat, end_beat, tempo):
        return assess_timed_window(
            phrase, hand, self._require(tempo), played,
            from_beat=from_beat, end_beat=end_beat,
            grade_note_holds=self.grade_note_holds)

    def live(self, phrase, *, hand, bpm, played, from_beat,
             elapsed_seconds, tempo):
        return timed_live_marks(
            phrase, hand, self._require(tempo), played, from_beat=from_beat,
            elapsed_seconds=elapsed_seconds,
            grade_note_holds=self.grade_note_holds)



@dataclass(frozen=True)
class PracticeAssessmentPolicies:
    """Injection point for the fixed and shaped timing implementations."""
    fixed: PracticeTimingPolicy
    mapped: PracticeTimingPolicy

    @classmethod
    def defaults(cls, assessment: AssessmentService, *,
                 grade_note_holds: bool = False) -> "PracticeAssessmentPolicies":
        return cls(FixedTimingPolicy(assessment, grade_note_holds),
                   MappedTimingPolicy(grade_note_holds))

    def select(self, tempo: TempoMap | None) -> PracticeTimingPolicy:
        return self.fixed if tempo is None else self.mapped

    def live_projection(self, phrase: Phrase, *, hand: str, bpm: float,
                        played: Sequence[PlayedNote], from_beat: float,
                        elapsed_seconds: float,
                        tempo: TempoMap | None) -> list[dict]:
        """Project live note status with the one selected grading policy.

        A held key inside the grader's release tolerance remains pending
        in the UI. This does not change the eventual graded release verdict
        or any durable assessment.
        """
        try:
            marks = self.select(tempo).live(
                phrase, hand=hand, bpm=bpm, played=played,
                from_beat=from_beat, elapsed_seconds=elapsed_seconds,
                tempo=tempo)
        except (ValueError, RuntimeError, KeyError):
            return []
        for mark in marks:
            until = mark.pop("hold_tolerance_until", None)
            if (until is not None and elapsed_seconds <= until
                    and (mark.get("dimensions") or {}).get("release") == "unreleased"):
                mark["dimensions"] = {**mark["dimensions"], "release": None}
        return marks

    @staticmethod
    def project(result: Assessment, phrase: Phrase, *, bpm: float,
                from_beat: float, tempo: TempoMap | None) -> dict:
        elapsed_to_beat = None
        if tempo is not None:
            offset = tempo.seconds_at(from_beat)
            elapsed_to_beat = lambda seconds: tempo.beat_at(offset + seconds)
        return project_assessment(
            result, phrase, bpm, played_from_beat=from_beat,
            elapsed_to_beat=elapsed_to_beat)

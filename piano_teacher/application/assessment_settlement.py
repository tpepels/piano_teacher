"""Grade one completed take and prepare its visible feedback.

No engine access, transport mutation, persistence, or lesson routing.
Grading occurs before engraving lookup; if engraving projection fails, the
graded result is retained and reported as unmapped rather than discarded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from ..exercise_contracts import TempoMap
from ..music import Phrase
from ..practice import Assessment, PlayedNote
from .practice_assessment import PracticeAssessmentPolicies


@dataclass(frozen=True)
class AssessedTake:
    result: Assessment
    marks: list[dict]
    unmapped: int
    feedback: str


def assess_completed_take(
    *, phrase: Phrase, hand: str, bpm: float,
    played: Sequence[PlayedNote], from_beat: float, end_beat: float,
    tempo: TempoMap | None, policies: PracticeAssessmentPolicies,
    layout_for_feedback: Callable[[], dict],
) -> AssessedTake:
    """Grade first, then try to map feedback to the retained score layout."""
    result = policies.select(tempo).grade(
        phrase, hand=hand, bpm=bpm, played=played,
        from_beat=from_beat, end_beat=end_beat, tempo=tempo)
    try:
        projection = policies.project(
            result, phrase, bpm=bpm, layout=layout_for_feedback(),
            from_beat=from_beat, tempo=tempo)
        marks = projection["marks"]
        unmapped = projection["unmapped"]
    except (ValueError, RuntimeError, KeyError) as exc:
        return AssessedTake(
            result=result, marks=[], unmapped=len(result.notes),
            feedback=f"Engraving feedback unavailable: {exc}")
    return AssessedTake(
        result=result, marks=marks, unmapped=unmapped,
        feedback=result.summary)

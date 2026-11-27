"""Grade one completed take and prepare its visible feedback.

No engine access, transport mutation, persistence, or lesson routing.
Feedback is carried by canonical musical identity.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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
) -> AssessedTake:
    """Grade the take and report source-note observations."""
    result = policies.select(tempo).grade(
        phrase, hand=hand, bpm=bpm, played=played,
        from_beat=from_beat, end_beat=end_beat, tempo=tempo)
    projection = policies.project(result, phrase, bpm=bpm,
                                  from_beat=from_beat, tempo=tempo)
    return AssessedTake(result=result, marks=projection["marks"],
                        unmapped=projection["unmapped"], feedback=result.summary)

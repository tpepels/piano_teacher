"""Source-bound remedial assignment selection after assessed repeated errors.

A planner returns a *real exercise* and a source-measure interval, without
mutating the curriculum, earning mastery, or touching MIDI/transport state.
The application may route the assignment to guided key-finding or a timed
partial retry. These two modes keep the existing source-note binding.
"""
from __future__ import annotations

from dataclasses import dataclass


from .exercise_generator import ExerciseVariant
from .measure_grid import phrase_grid
from .music import Phrase



@dataclass(frozen=True)
class RemedialAssignment:
    action: str
    focus: str
    start_beat: float
    end_beat: float
    variant: ExerciseVariant
    stage_key: str
    reason: str
    transformed_rhythm: bool = False

    @property
    def guided(self) -> bool:
        return self.action == "note-isolation"


@dataclass(frozen=True)
class TimedRemedialReview:
    """Validated source-measure interval for a timed partial retry."""
    start_beat: float
    end_beat: float
    first_bar: int
    last_bar: int

    @property
    def retry_range(self) -> dict:
        return {
            "start_beat": self.start_beat,
            "end_beat": self.end_beat,
            "first_bar": self.first_bar,
            "last_bar": self.last_bar,
        }


def plan_timed_remedial_review(
    assignment: RemedialAssignment, phrase: Phrase,
    boundaries: tuple[float, ...],
) -> TimedRemedialReview:
    """Validate before transport is interrupted or an active take is reset."""
    grid = phrase_grid(phrase, boundaries)
    try:
        start_index = grid.index(assignment.start_beat)
        end_index = grid.index(assignment.end_beat)
    except ValueError as exc:
        raise ValueError("Remedial section must align with source measures") from exc
    if not 0 <= start_index < end_index < len(grid):
        raise ValueError("Remedial section must span at least one source measure")
    return TimedRemedialReview(
        start_beat=assignment.start_beat, end_beat=assignment.end_beat,
        first_bar=phrase.first_bar + start_index,
        last_bar=phrase.first_bar + end_index - 1,
    )

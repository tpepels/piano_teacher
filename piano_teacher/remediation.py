"""Source-bound remedial assignment selection after assessed repeated errors.

A planner returns a *real exercise* and a source-measure interval, without
mutating the curriculum, earning mastery, or touching MIDI/transport state.
The application may route the assignment to guided key-finding or a timed
partial retry. These two modes keep the existing source-note binding.
"""
from __future__ import annotations

from dataclasses import dataclass


from .exercise_generator import ExerciseVariant



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

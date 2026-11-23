"""Source-stage selection without transport, teaching, or score ownership.

Validation of explicit step numbers precedes stopping a live take. The
LearningPlan mutation is executed by the engine under its existing lock.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..lesson_settings import SETTINGS


@dataclass(frozen=True)
class StageChange:
    action: str
    number: int | None = None
    hand: str | None = None
    bpm: Any = None

    @property
    def tempo_only(self) -> bool:
        return self.action in ("tempo", "tempo_up", "tempo_down")

def prepare_stage_change(plan, action: str, values: dict) -> StageChange:
    """Validate stage intent before cancelling any active take or feedback."""
    if action == "select_step":
        number = values.get("number")
        if (isinstance(number, bool) or not isinstance(number, (int, float, str))
                or (isinstance(number, float) and not number.is_integer())):
            raise ValueError("Choose a whole lesson step number")
        try:
            number = int(number)
        except ValueError:
            raise ValueError("Choose a whole lesson step number") from None
        if not 1 <= number <= len(plan.lesson_steps):
            raise ValueError("Lesson step out of bounds")
        return StageChange(action=action, number=number)
    if action == "hand":
        requested = str(values.get("hand", "both"))
        if requested not in plan.hands:
            raise ValueError(f"Hand {requested!r} unavailable")
        return StageChange(action=action, hand=requested)
    if action == "tempo":
        bpm = values.get("bpm")
        if (isinstance(bpm, bool) or not isinstance(bpm, (int, float, str))
                or (isinstance(bpm, float) and not bpm.is_integer())):
            raise ValueError("Choose a whole BPM value")
        try:
            bpm = int(bpm)
        except ValueError:
            raise ValueError("Choose a whole BPM value") from None
        if not SETTINGS.minimum_bpm <= bpm <= SETTINGS.maximum_bpm:
            raise ValueError(
                f"BPM must be between {SETTINGS.minimum_bpm} and {SETTINGS.maximum_bpm}")
        return StageChange(action=action, bpm=bpm)
    if action not in ("next", "previous", "tempo_up", "tempo_down"):
        raise ValueError(f"Unsupported action: {action}")
    return StageChange(action=action)


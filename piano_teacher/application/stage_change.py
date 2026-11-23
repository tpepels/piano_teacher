"""Source-stage selection without transport, teaching, or score ownership.

Validation of explicit step numbers precedes stopping a live take. The
LearningPlan mutation is executed by the engine under its existing lock.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..lesson_settings import SETTINGS
from ..teaching_course import warmup_unlocked_step


@dataclass(frozen=True)
class StageChange:
    action: str
    number: int | None = None
    hand: str | None = None
    bpm: Any = None

    @property
    def tempo_only(self) -> bool:
        return self.action in ("tempo", "tempo_up", "tempo_down")

def _require_hand_change(plan, requested: str, *, warmup: bool) -> None:
    if requested not in plan.hands:
        raise ValueError(f"Hand {requested!r} unavailable")
    if warmup and requested != plan.hand:
        # Stage identities, not the numeric hand index in a potentially
        # multi-exercise catalog, determine which hand is unlocked.
        first = next((number for number, step in enumerate(plan.lesson_steps, 1)
                      if step.exercise_index == plan.index and
                      step.hand == requested), None)
        if first is None or first > warmup_unlocked_step(plan.course_state()):
            raise ValueError("Complete three clean passes to unlock the next hand")


def prepare_stage_change(plan, action: str, values: dict, *,
                         warmup: bool = False) -> StageChange:
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
        if warmup and number > warmup_unlocked_step(plan.course_state()):
            raise ValueError("Complete three clean passes to unlock the next warm-up step")
        return StageChange(action=action, number=number)
    if action == "hand":
        requested = str(values.get("hand", "both"))
        _require_hand_change(plan, requested, warmup=warmup)
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
    if warmup and action == "next" and plan.index+1 < len(plan.exercises):
        first = next((number for number, step in enumerate(plan.lesson_steps, 1)
                      if step.exercise_index == plan.index+1), None)
        if first is None or first > warmup_unlocked_step(plan.course_state()):
            raise ValueError("Complete three clean passes to unlock the next warm-up passage")
    return StageChange(action=action)


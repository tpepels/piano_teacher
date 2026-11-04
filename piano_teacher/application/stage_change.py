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

    @property
    def resets_open_position(self) -> bool:
        return self.action in ("select_step", "next", "previous", "hand")


def _require_hand_change(plan, requested: str, *, warmup: bool) -> None:
    if requested not in plan.hands:
        raise ValueError(f"Hand {requested!r} unavailable")
    if warmup and plan.hands.index(requested) > plan.hand_index:
        previous_step = plan.lesson_steps[plan.hands.index(requested) - 1]
        if previous_step.key not in plan.mastered:
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
    return StageChange(action=action)


def apply_stage_change(plan, change: StageChange, *, warmup: bool) -> None:
    """Change only the LearningPlan, never clocks, scores or learner writes."""
    action = change.action
    if action == "select_step":
        plan.select_step(change.number)
    elif action == "next":
        plan.jump(1)
    elif action == "previous":
        plan.jump(-1)
    elif action == "hand":
        requested = change.hand
        _require_hand_change(plan, requested, warmup=warmup)
        plan.set_hand(requested)
    elif action == "tempo":
        plan.set_bpm(int(change.bpm))
    elif action == "tempo_up":
        plan.increase_tempo()
    elif action == "tempo_down":
        plan.decrease_tempo()
    else:
        raise ValueError(f"Unsupported action: {action}")


@dataclass(frozen=True)
class GuidedReentry:
    route: str
    recovery: bool = False
    explicit_learn: bool = False


def guided_reentry(
    *, change: StageChange, was_guided: bool, course_guided: bool,
    previous_return: tuple[str, float] | None, current_stage: str,
) -> GuidedReentry:
    """Choose the next teaching stage without touching transport/revisions.

    A tempo change in recovery keeps the source retry anchor only when
    the stage identity remains unchanged.
    """
    if not was_guided:
        return GuidedReentry("none")
    if change.tempo_only:
        return GuidedReentry(
            "same_fragment",
            recovery=(previous_return is not None
                      and previous_return[0] == current_stage))
    if course_guided:
        return GuidedReentry(
            "course", explicit_learn=change.action == "hand")
    return GuidedReentry("fresh")

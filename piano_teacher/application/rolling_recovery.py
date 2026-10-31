"""Pure recovery-tempo and escalation plan for a detected source-grid failure.

Only the engine mutates MIDI state, persists trouble, and schedules rewind.
This value object carries the chosen tempo, repeat history and UI projection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..lesson_settings import SETTINGS
from ..recovery_projection import RecoveryDisplay, recovery_display
from ..recovery import RecoveryDecision


@dataclass(frozen=True)
class RollingRecoveryTransition:
    bpm: int
    trouble_key: tuple
    trouble_count: int
    guided: bool
    display: RecoveryDisplay


def plan_rolling_recovery(decision: RecoveryDecision, *, identity: str,
                          bpm: int, previous_key: tuple | None,
                          previous_count: int, grid: Sequence[float],
                          first_bar: int, now: float,
                          allow_guided: bool = True) -> RollingRecoveryTransition:
    new_bpm = max(SETTINGS.minimum_bpm,
                  round(bpm * SETTINGS.recovery_tempo_multiplier))
    key = identity, decision.restart_beat, decision.end_beat
    count = previous_count + 1 if key == previous_key else 1
    guided = allow_guided and count >= SETTINGS.guided_recovery_after_failures
    display = recovery_display(
        decision, grid=grid, first_bar=first_bar,
        before_bpm=bpm, after_bpm=new_bpm, now=now, guided=guided)
    return RollingRecoveryTransition(new_bpm, key, count, guided, display)

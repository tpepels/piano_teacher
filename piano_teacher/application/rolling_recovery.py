"""Route MIDI-grid failure evidence through a registered response policy.

This adapter joins metrical source selection to the existing immutable
recovery display. The engine alone applies decisions and owns transport.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from ..lesson_settings import SETTINGS
from ..recovery_projection import RecoveryDisplay, recovery_display
from ..recovery import RecoveryDecision
from .mistake_responses import resolve_mistake_policy, rolling_response


@dataclass(frozen=True)
class RollingRecoveryTransition:
    bpm: int
    trouble_key: tuple
    trouble_count: int
    guided: bool
    display: RecoveryDisplay
    restart_beat: float
    mode: str
    action: str = "repair"
    reason: str = "registered_policy"


def plan_rolling_recovery(decision: RecoveryDecision, *, identity: str,
                          bpm: int, previous_key: tuple | None,
                          previous_count: int, grid: Sequence[float],
                          first_bar: int, now: float,
                          allow_guided: bool = True,
                          strategy: str = "adaptive", context=None) -> RollingRecoveryTransition:
    policy = resolve_mistake_policy(strategy)
    chosen = rolling_response(
        policy, decision, identity=identity, bpm=bpm,
        minimum_bpm=SETTINGS.minimum_bpm,
        previous_key=previous_key, previous_count=previous_count,
        grid=grid, allow_guided=allow_guided, context=context)
    adjusted = replace(decision, restart_beat=chosen.restart_beat)
    display = recovery_display(
        adjusted, grid=grid, first_bar=first_bar,
        before_bpm=bpm, after_bpm=chosen.bpm, now=now,
        guided=chosen.guided)
    if strategy != "adaptive":
        notice = dict(display.notice)
        notice["kind"] = "slowdown" if chosen.bpm < bpm else "repeat"
        notice["response"] = strategy
        if strategy == "steady-repeat":
            instruction = display.next_action
        elif strategy == "finish-then-review":
            instruction = "Finish the phrase; review errors after the take."
        else:
            instruction = display.next_action
        display = replace(display, notice=notice, next_action=instruction)
    return RollingRecoveryTransition(
        chosen.bpm, chosen.trouble_key, chosen.count, chosen.guided,
        display, chosen.restart_beat, chosen.mode, chosen.action, chosen.reason)

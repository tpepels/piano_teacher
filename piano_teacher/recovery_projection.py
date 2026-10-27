"""Pure recovery HUD and section metadata; no engine state or MIDI dependency.

Recovery detection remains in recovery.py. PracticeEngine alone decides when
to apply the result and updates clocks, tempo, learner progress and persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .measure_grid import bar_number_at
from .recovery import RecoveryDecision


@dataclass(frozen=True)
class RecoveryDisplay:
    notice: dict
    retry_range: dict
    feedback: str
    next_action: str


def recovery_display(
    decision: RecoveryDecision, *, grid: Sequence[float], first_bar: int,
    before_bpm: int, after_bpm: int, now: float, guided: bool,
) -> RecoveryDisplay:
    """Project an accepted failure decision onto its canonical source bars."""
    start_bar = bar_number_at(grid, decision.restart_beat, first_bar)
    final_bar = first_bar + next(
        index for index, beat in enumerate(grid)
        if abs(beat-decision.end_beat) < 1e-6) - 1
    retry_range = {
        "first_bar": start_bar, "last_bar": final_bar,
        "start_beat": decision.restart_beat, "end_beat": decision.end_beat,
    }
    notice = {
        "kind": "slowdown", "errors": decision.errors,
        "missed": decision.missed, "wrong": decision.wrong,
        "from_bpm": before_bpm, "to_bpm": after_bpm,
        "first_bar": start_bar,
        "last_bar": bar_number_at(
            grid, max(decision.restart_beat, decision.end_beat-1e-6), first_bar),
        "expires_at": now+9.0,
    }
    feedback = (f"{decision.errors} wrong or missed notes - retrying from "
                f"measure {start_bar} at {after_bpm} BPM")
    bars = f"{start_bar}-{final_bar}"
    next_action = (f"Learn bars {bars} slowly, then retry the rhythm."
                   if guided else f"Retry bars {bars} at {after_bpm} BPM.")
    return RecoveryDisplay(
        notice=notice, retry_range=retry_range,
        feedback=feedback, next_action=next_action)

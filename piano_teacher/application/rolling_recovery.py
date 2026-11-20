"""Route MIDI-grid failure evidence through a registered response policy.

This adapter joins metrical source selection to the existing immutable
recovery display. The engine alone applies decisions and owns transport.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..recovery_projection import RecoveryDisplay, recovery_display


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
    uses_completed_rest: bool = False

    @property
    def feedback(self) -> str:
        return ("Practice paused · "+self.reason
                if self.action == "pause" else self.display.feedback)

    @property
    def next_action(self) -> str:
        return self.display.next_action if self.action == "repair" else self.reason


def project_rolling_response(chosen, decision, *, grid, first_bar, before_bpm, now,
                             same_stage: bool, source_duration: float):
    """Project an already selected response; never choose policy or tempo."""
    display = recovery_display(replace(decision,restart_beat=chosen.restart_beat),
        grid=grid,first_bar=first_bar,before_bpm=before_bpm,after_bpm=chosen.bpm,
        now=now,guided=chosen.guided)
    if chosen.mode != "adaptive":
        notice = dict(display.notice)
        notice.update(kind="slowdown" if chosen.bpm < before_bpm else "repeat",response=chosen.mode)
        display = replace(display,notice=notice)
    return RollingRecoveryTransition(chosen.bpm,chosen.trouble_key,chosen.count,
        chosen.guided,display,chosen.restart_beat,chosen.mode,chosen.action,chosen.reason,
        not chosen.guided and chosen.action != "pause" and same_stage
        and decision.end_beat >= source_duration-1e-7)

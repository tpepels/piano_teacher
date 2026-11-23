"""One worker tick's musical transition, in a fixed order.

Observe (device, calibration, evidence phase); replay an admitted rolling
recovery; apply a non-grading transition; otherwise progress the running
take. Each step belongs to its own owner; this class only orders them.
"""
from __future__ import annotations


class PracticeTimeline:
    def __init__(self, *, observations, transitions, progression):
        self.observations = observations
        self.transitions = transitions
        self.progression = progression

    def update_transition(self) -> bool:
        """Advance the backend clock under its existing session lock."""
        now = self.observations.observe()
        if self.progression.replay_rolling(now):
            return False
        consumed, followup = self.transitions.run(now)
        if consumed or followup:
            return followup
        return self.progression.advance(now)

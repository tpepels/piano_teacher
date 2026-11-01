"""Pure score-revision acknowledgement precedence.

Score generation, transport, demo audio, and teaching-controller mutations
remain with their existing owners. Delayed responses must never start a
new passage or consume a paused revision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ScoreAckAction = Literal["ignore", "defer", "listen", "learn", "practice"]


@dataclass(frozen=True)
class ScoreAckState:
    requested_revision: int | None
    current_revision: int
    paused: bool
    mode: str
    teaching_bound: bool


def choose_score_ack_action(revision: int, state: ScoreAckState) -> ScoreAckAction:
    if (state.requested_revision != revision
            or state.current_revision != revision):
        return "ignore"
    if state.paused:
        return "defer"
    if state.mode == "listen":
        return "listen"
    if state.mode == "learn" and state.teaching_bound:
        return "learn"
    return "practice"

"""Transport-command decisions independent of application state mutation.

All deadlines, MIDI recording, score revisions and held-key state are still
executed by PracticeEngine/VisualTransport under the existing session lock.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StartRoute = Literal["listen", "prepare_practice", "reload_score", "rewind", "start"]
PAUSABLE_PHASES = frozenset((
    "playing", "count_in", "feedback", "recovering",
    "loading", "guided_wait", "preview_gap"))


@dataclass(frozen=True)
class StartFacts:
    action: str
    mode: str
    loaded: bool
    source_changed: bool
    exercise_kind: str | None


def select_start_route(facts: StartFacts) -> StartRoute:
    if facts.mode == "listen":
        return "listen"
    if facts.mode == "learn":
        return "prepare_practice"
    if facts.loaded and facts.source_changed:
        return "reload_score"
    if (facts.action == "restart" and facts.loaded
            and facts.mode == "practice" and facts.exercise_kind != "perform"):
        return "rewind"
    return "start"


def require_pausable(*, paused: bool, phase: str) -> None:
    if paused:
        raise ValueError("Cannot pause an exercise that is already paused")
    if phase not in PAUSABLE_PHASES:
        raise ValueError("Cannot pause unless an exercise is playing or preparing")


def resume_timeline(*, paused: bool, learning: bool, running: bool,
                    preview_pending: bool, automatic_feedback: bool) -> bool:
    """Return whether the running count-in deadline must shift."""
    if not paused:
        raise ValueError("Cannot resume unless an exercise is paused")
    return not learning and (running or preview_pending or automatic_feedback)

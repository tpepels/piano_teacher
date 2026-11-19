"""Transport-command decisions independent of application state mutation.

All deadlines, MIDI recording, score revisions and held-key state are still
executed by PracticeEngine/VisualTransport under the existing session lock.
"""
from __future__ import annotations

PAUSABLE_PHASES = frozenset((
    "playing", "count_in", "feedback", "recovering",
    "loading", "guided_wait", "preview_gap", "admitting"))


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



"""Transport-command decisions independent of application state mutation.

All deadlines, MIDI recording, score revisions and held-key state are still
executed by PracticeEngine/VisualTransport under the existing session lock.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

PAUSABLE_PHASES = frozenset((
    "playing", "count_in", "feedback", "recovering",
    "loading", "guided_wait", "preview_gap"))


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


def scheduled_offscreen_start(deadline: float, lead_beats: float,
                              bpm: float) -> float:
    """One future MIDI deadline for an already engraved lesson handoff.

    The UI supplies the entire offscreen reading horizon including its
    header. The engine applies it to its own graded transport; no second
    scrolling timeline or speculative on-screen source insertion exists.
    """
    if not (math.isfinite(deadline) and math.isfinite(lead_beats)
            and math.isfinite(bpm) and 0.0 <= lead_beats <= 64.0
            and bpm > 0.0):
        raise ValueError("Invalid future notation reading lead")
    return deadline + lead_beats * 60.0 / bpm



def planned_retry_reverse_seconds(
    *, reading_lead_seconds: float, semantic_rest_seconds: float,
) -> float:
    """Place the graded retry at the already engraved world's future onset.

    The visible preparation contains one genuine written empty measure.
    Subtract that measure from the supplied total lead. The prior implementation
    treated the total lead as just the reverse-animation duration and inserted
    the entire rest AGAIN, making the sound/score start late by one measure.

    No-UI engine calls still use their established intrinsic preparation
    schedule; this function applies only to an explicitly reserved world onset.
    """
    values = (reading_lead_seconds, semantic_rest_seconds)
    if not all(math.isfinite(v) for v in values) or (
        reading_lead_seconds <= 0 or semantic_rest_seconds <= 0):
        raise ValueError("Invalid scheduled retry time")
    available = reading_lead_seconds - semantic_rest_seconds
    # The reserved deadline is honoured exactly (round 4): the reverse
    # animation shrinks to what the reservation leaves, down to a frame,
    # and never pushes the take later than the ink Godot admitted.
    if available + 0.01 < 0.05:
        raise ValueError("Future retry reservation lacks space for one full rest")
    return max(0.05, available)

"""Transport-command decisions independent of application state mutation.

All deadlines, MIDI recording, score revisions and held-key state are still
executed by PracticeEngine/VisualTransport under the existing session lock.
"""
from __future__ import annotations
from dataclasses import dataclass
from .musical_scheduler import SCHEDULER

PAUSABLE_PHASES = frozenset((
    "playing", "count_in", "feedback", "recovering",
    "loading", "guided_wait", "introducing", "disconnected",
    "preview_gap", "admitting"))


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


@dataclass(frozen=True, slots=True)
class ResumeTiming:
    origin: float
    grading_after: float
    count_in_beats: float


def resume_timing(*, now: float, origin: float, previous_origin: float,
                  paused_at: float, frozen_seconds: float | None,
                  grading_after: float, had_reading_lead: bool,
                  shift_run_at: bool, running: bool, mode: str,
                  pause_context: str | None, bpm: float | None,
                  count_in_beats: float, full_count_in_beats: float, bar_beats: float,
                  reading_lead_seconds: float,
                  midi_connected: bool, preview: bool,
                  scheduled_deadline: float | None) -> ResumeTiming:
    """Apply the existing scheduler to the single shifted source epoch."""
    if (shift_run_at and running and bpm is not None
            and mode in ("practice", "perform")
            and pause_context in ("playing", "count_in")):
        if reading_lead_seconds > 0.0:
            count_in_beats = full_count_in_beats
            origin, grading_after = SCHEDULER.resume_playing(
                now=now,origin=origin,bpm=bpm,count_in_beats=count_in_beats,
                reading_lead_seconds=reading_lead_seconds,
                already_waiting=max(0.,grading_after-now))
        elif (midi_connected and not preview and pause_context == "playing"
              and not had_reading_lead and origin <= now):
            count_in_beats = SCHEDULER.count_in_beats(full_count_in_beats,bpm)
            lead = SCHEDULER.beats_seconds(count_in_beats,bpm)
            origin += lead
            grading_after = now+lead
    if scheduled_deadline is not None and shift_run_at and running:
        frozen = (frozen_seconds if frozen_seconds is not None
                  else max(0.0,paused_at-previous_origin))
        origin = scheduled_deadline-max(0.0,frozen)
        grading_after = scheduled_deadline
    return ResumeTiming(origin,grading_after,count_in_beats)



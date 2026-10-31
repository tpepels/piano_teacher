"""Tempo-sensitive grading tolerance shared by final scoring and MIDI previews."""
from __future__ import annotations

from .lesson_settings import SETTINGS


def onset_tolerance(seconds_per_beat: float) -> float:
    """About 225 ms at 40 BPM, falling to 100 ms at 120 BPM."""
    return max(SETTINGS.grading_onset_tolerance_seconds,
               min(0.25, 0.15 * seconds_per_beat))


def duration_tolerance(duration_seconds: float, seconds_per_beat: float) -> float:
    """Relax key-release precision at slower practice speeds."""
    fraction = max(SETTINGS.grading_duration_tolerance_fraction,
                   min(0.65, SETTINGS.grading_duration_tolerance_fraction
                       + 0.45 * max(0.0, seconds_per_beat - 0.5)))
    return max(SETTINGS.grading_duration_floor_seconds,
               duration_seconds * fraction)

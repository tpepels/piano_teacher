"""Tempo-sensitive grading tolerance shared by final scoring and MIDI previews."""
from __future__ import annotations

from .lesson_settings import SETTINGS


def onset_tolerance(seconds_per_beat: float) -> float:
    """A gentler 300ms ceiling for slow lessons, 130ms at full tempo."""
    return max(SETTINGS.grading_onset_tolerance_seconds,
               min(0.30, 0.20 * seconds_per_beat))


def duration_tolerance(duration_seconds: float, seconds_per_beat: float) -> float:
    """Relax key-release precision at slower practice speeds."""
    fraction = max(SETTINGS.grading_duration_tolerance_fraction,
                   min(0.75, SETTINGS.grading_duration_tolerance_fraction
                       + 0.28 * max(0.0, seconds_per_beat - 0.5)))
    return max(SETTINGS.grading_duration_floor_seconds,
               duration_seconds * fraction)

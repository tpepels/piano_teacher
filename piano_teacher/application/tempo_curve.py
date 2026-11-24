"""Exact beat <-> time conversion for one tempo span, constant or eased.

A tempo change between takes is an eased ramp (owner decision 2026-11-24):
the speed follows half a cosine from v0 to v1 over L beats,

    v(u) = v0 + (v1 - v0) * (1 - cos(pi*u)) / 2,   u = beats / L in [0, 1],

which starts and ends gently. Time and position have closed forms, so the
scrolling bar, the clicks and grading share one exact mapping:

    t(u) = 120 L / (pi * sqrt(v0 v1)) * atan(sqrt(v1/v0) * tan(pi u / 2))
    u(t) = (2/pi) * atan(tan(theta) / sqrt(v1/v0)),
           theta = pi * t * sqrt(v0 v1) / (120 L)

The whole ramp takes 60 L / sqrt(v0 v1) seconds (L beats at the geometric
mean tempo); with v0 == v1 everything reduces to 60 * beats / v.
godot/tempo_curve.gd implements the same functions for drawing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TempoSpan:
    """`beats` of music whose tempo goes from `start_bpm` to `end_bpm`."""
    beats: float
    start_bpm: float
    end_bpm: float

    def __post_init__(self):
        if not (math.isfinite(self.beats) and self.beats >= 0
                and self.start_bpm > 0 and self.end_bpm > 0):
            raise ValueError("Invalid tempo span")

    @property
    def constant(self) -> bool:
        return abs(self.end_bpm - self.start_bpm) < 1e-9

    def bpm_at(self, beat: float) -> float:
        """Tempo after `beat` beats of this span."""
        if self.constant or self.beats <= 0:
            return self.start_bpm
        u = min(1.0, max(0.0, beat / self.beats))
        return self.start_bpm + (self.end_bpm - self.start_bpm) * (1 - math.cos(math.pi*u)) / 2

    def seconds_at(self, beat: float) -> float:
        """Seconds from the span's start until `beat` beats into it."""
        beat = min(self.beats, max(0.0, beat))
        if self.constant or self.beats <= 0:
            return 60.0 * beat / self.start_bpm
        v0, v1, length = self.start_bpm, self.end_bpm, self.beats
        u = beat / length
        if u >= 1.0:
            return 60.0 * length / math.sqrt(v0 * v1)
        return (120.0 * length / (math.pi * math.sqrt(v0 * v1))
                * math.atan(math.sqrt(v1 / v0) * math.tan(math.pi * u / 2)))

    @property
    def seconds(self) -> float:
        return self.seconds_at(self.beats)

    def beat_at(self, seconds: float) -> float:
        """Beats into the span after `seconds` (clamped to the span)."""
        if seconds <= 0:
            return 0.0
        if seconds >= self.seconds:
            return self.beats
        if self.constant:
            return seconds * self.start_bpm / 60.0
        v0, v1, length = self.start_bpm, self.end_bpm, self.beats
        theta = math.pi * seconds * math.sqrt(v0 * v1) / (120.0 * length)
        u = (2 / math.pi) * math.atan(math.tan(theta) / math.sqrt(v1 / v0))
        return u * length


def count_in_spans(bar_beats: float, from_bpm: float, to_bpm: float) -> tuple[TempoSpan, ...]:
    """The count-in bar between takes: an eased ramp over its first half,
    then the new tempo, so the last clicks give the exact new pulse."""
    if abs(to_bpm - from_bpm) < 1e-9:
        return (TempoSpan(bar_beats, to_bpm, to_bpm),)
    half = bar_beats / 2
    return (TempoSpan(half, from_bpm, to_bpm), TempoSpan(bar_beats - half, to_bpm, to_bpm))


def spans_seconds(spans) -> float:
    return sum(span.seconds for span in spans)

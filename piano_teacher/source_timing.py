"""Semantic practice silence, separate from canonical source notation.

Preparation uses the UPCOMING measure's full nominal meter and context,
except that an abbreviated opening immediately followed by a normal meter
uses that meter for preparation, following lesson_timing.preparation_meter.
The original incoming meter remains explicit as source_meter. Source notes
and measures retain their canonical pickup timing.
The preparation context is established at gap START. If its meter differs
from source_meter, the canonical opening meter returns at the source opening
as a genuine musical change. A shortened final bar never defines this gap.
This deliberately supersedes the old final-bar rule.
All coordinates and durations are quarter-note beats; no BPM enters here.
"""
from __future__ import annotations

import math
from fractions import Fraction

from .lesson_timing import preparation_meter
from .measure_grid import phrase_grid
from .music import Phrase, Piece

SCHEMA = "piano-teacher-practice-timeline-v1"
# Unloaded-state placeholder only: loaded gaps always come from source meter.
# Used by both transport state and its snapshot projection.
UNLOADED_METER = (4, 4)
UNLOADED_GAP_BEATS = UNLOADED_METER[0] * 4.0 / UNLOADED_METER[1]


def source_meter(beat: float, length: float, signatures) -> tuple[int, int]:
    active = [(n, d) for offset, n, d in signatures if offset <= beat + 1e-7]
    if active:
        return active[-1]
    fraction = Fraction(length).limit_denominator(16)
    if abs(float(fraction) - length) > .005:
        raise ValueError(f"Cannot express source bar duration: {length}")
    return fraction.numerator, 4 * fraction.denominator


def selected_practice_timeline(piece: Piece, phrase: Phrase) -> dict:
    grid = phrase_grid(phrase, piece.bar_boundaries)
    signatures = sorted(piece.time_signatures)
    # Only the opening and adjacent measure determine the upcoming gap.
    measures = [
        {"start_beat": start, "end_beat": end,
         "meter": source_meter(phrase.start + start, end - start, signatures)}
        for start, end in zip(grid[:2], grid[1:3], strict=False)
    ]
    sounding = round(phrase.sounding_end - phrase.start, 8)
    gap = preparation_measure_descriptor(measures[0], sounding,
        following_measure=measures[1] if len(measures) == 2 else None)
    return {"schema": SCHEMA, "source_duration_beats": grid[-1],
            "sounding_duration_beats": sounding,
            "stride_beats": gap["end_beat"], "gap": gap}


def _preparation_duration(meter) -> float:
    numerator, denominator = meter
    if any(not math.isfinite(value) or value <= 0 for value in meter):
        raise ValueError("Practice preparation needs a finite positive meter")
    duration = numerator * 4.0 / denominator
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Practice preparation needs a finite positive duration")
    return duration


def preparation_measure_descriptor(measure, start_beat: float,
                                   staff_order=("right", "left"), *,
                                   following_measure=None) -> dict:
    """One full silent measure inheriting the upcoming source context."""
    context = measure
    numerator, denominator = context["meter"]
    duration = _preparation_duration((numerator, denominator))
    if not math.isfinite(start_beat):
        raise ValueError("Practice preparation needs a finite position")
    source_meter = [numerator, denominator]
    if following_measure is not None:
        following = following_measure
        # Only the adjacent source measure can establish a pickup's normal
        # meter. Do not scan across real 1/8 bars to a later meter change.
        if abs(following["start_beat"] - context["end_beat"]) <= 1e-7:
            _preparation_duration(following["meter"])
            numerator, denominator = preparation_meter(
                (numerator, denominator),
                ((following["start_beat"], *following["meter"]),),
                context["start_beat"])
            duration = _preparation_duration((numerator, denominator))
    end_beat = start_beat + duration
    if not math.isfinite(end_beat) or end_beat <= start_beat:
        raise ValueError("Practice preparation needs a finite positive span")
    return {
        "kind": "measure_rest", "origin": "practice",
        "start_beat": start_beat, "end_beat": end_beat,
        "duration_beats": duration,
        "meter": [numerator, denominator], "source_meter": source_meter,
        "staves": list(staff_order), "full_measure": True,
        "note_type": "whole", "dots": 0,
        "left_barline": {"style": "regular", "repeat": ""},
        "right_barline": {"style": "regular", "repeat": ""},
        "events": [
            {"id": f"practice:gap:{staff}", "source_id": None, "kind": "rest",
             "staff": staff, "duration_beats": duration, "full_measure": True,
             "is_attack": False, "graded": False}
            for staff in staff_order],
    }

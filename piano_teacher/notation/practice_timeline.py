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

from copy import deepcopy
from dataclasses import asdict, is_dataclass
import math

from ..lesson_timing import preparation_meter

SCHEMA = "piano-teacher-practice-timeline-v1"


def preparation_measure_descriptor(measure, start_beat: float,
                                   staff_order=("right", "left"), *,
                                   following_measure=None) -> dict:
    """One full silent measure inheriting the upcoming source context."""
    context = asdict(measure) if is_dataclass(measure) else measure
    numerator, denominator = context["meter"]
    if numerator <= 0 or denominator <= 0 or not math.isfinite(start_beat):
        raise ValueError("Practice preparation needs a positive meter and finite position")
    source_meter = [numerator, denominator]
    if following_measure is not None:
        following = (asdict(following_measure) if is_dataclass(following_measure)
                     else following_measure)
        # Only the adjacent source measure can establish a pickup's normal
        # meter. Do not scan across real 1/8 bars to a later meter change.
        if abs(following["start_beat"] - context["end_beat"]) <= 1e-7:
            numerator, denominator = preparation_meter(
                (numerator, denominator),
                ((following["start_beat"], *following["meter"]),),
                context["start_beat"])
    duration = numerator * 4.0 / denominator
    return {
        "kind": "measure_rest", "origin": "practice",
        "start_beat": start_beat, "end_beat": start_beat + duration,
        "duration_beats": duration,
        "meter": [numerator, denominator], "source_meter": source_meter,
        "keys": deepcopy(context["keys"]), "clefs": deepcopy(context["clefs"]),
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


def practice_timeline_descriptor(measures, duration_beats: float,
                                 staff_order=("right", "left")) -> dict:
    """Describe a source pass followed by preparation for its FIRST measure."""
    if not measures or not math.isfinite(duration_beats) or duration_beats <= 0:
        raise ValueError("Practice timeline needs source measures and positive duration")
    gap = preparation_measure_descriptor(
        measures[0], duration_beats, staff_order,
        following_measure=measures[1] if len(measures) > 1 else None)
    return {"schema": SCHEMA, "source_duration_beats": duration_beats,
            "stride_beats": gap["end_beat"], "gap": gap}

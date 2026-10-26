"""Semantic practice silence, separate from canonical source notation.

Preparation uses the UPCOMING measure's full nominal meter and context.
In particular, final-to-initial context restoration happens at gap START,
not at the next source opening. Neither a pickup nor a shortened final bar
changes this duration. This deliberately supersedes the old final-bar rule.
All coordinates and durations are quarter-note beats; no BPM enters here.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
import math

SCHEMA = "piano-teacher-practice-timeline-v1"


def preparation_measure_descriptor(measure, start_beat: float,
                                   staff_order=("right", "left")) -> dict:
    """One full silent measure inheriting the upcoming source context."""
    context = asdict(measure) if is_dataclass(measure) else measure
    numerator, denominator = context["meter"]
    if numerator <= 0 or denominator <= 0 or not math.isfinite(start_beat):
        raise ValueError("Practice preparation needs a positive meter and finite position")
    duration = numerator * 4.0 / denominator
    return {
        "kind": "measure_rest", "origin": "practice",
        "start_beat": start_beat, "end_beat": start_beat + duration,
        "duration_beats": duration,
        "meter": [numerator, denominator],
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
    gap = preparation_measure_descriptor(measures[0], duration_beats, staff_order)
    return {"schema": SCHEMA, "source_duration_beats": duration_beats,
            "stride_beats": gap["end_beat"], "gap": gap}

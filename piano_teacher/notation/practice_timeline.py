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
# Unloaded-state placeholder only: loaded gaps always come from source meter.
# Used by both transport state and its snapshot projection.
UNLOADED_METER = (4, 4)
UNLOADED_GAP_BEATS = UNLOADED_METER[0] * 4.0 / UNLOADED_METER[1]


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
    context = asdict(measure) if is_dataclass(measure) else measure
    numerator, denominator = context["meter"]
    duration = _preparation_duration((numerator, denominator))
    if not math.isfinite(start_beat):
        raise ValueError("Practice preparation needs a finite position")
    source_meter = [numerator, denominator]
    if following_measure is not None:
        following = (asdict(following_measure) if is_dataclass(following_measure)
                     else following_measure)
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


def source_preparation_measure(source: dict, from_beat: float,
                               start_beat: float = 0.0) -> dict:
    """One canonical source context for both silent-rest and retry placement.

    The entire source's authored bar/meter sequence selects the measure.
    No renderer pixel clearance or transport deadline enters this function.
    """
    measures = source["measures"]
    if not measures:
        raise ValueError("Cannot prepare a retry without source measures")
    index = max(
        (i for i, item in enumerate(measures)
         if float(item["start_beat"]) <= from_beat+1e-7),default=0)
    following = measures[index+1] if index+1 < len(measures) else None
    return preparation_measure_descriptor(
        measures[index],start_beat,source["staff_order"],
        following_measure=following)


def retry_preparation_rest_beats(source: dict, from_beat: float) -> float:
    """Read the exact authored preparation meter from original score geometry.

    The retry's silent strip is source-metrical, including pickup and meter
    changes. It cannot be inferred from visual pixels or a generic 4/4 gap.
    This function is pure and never chooses or moves a playback deadline.
    """
    if not source["measures"]:
        return float(source["practice_timeline"]["gap"]["duration_beats"])
    return float(source_preparation_measure(
        source,from_beat,0.0)["duration_beats"])


def practice_timeline_descriptor(measures, duration_beats: float,
                                 staff_order=("right", "left"), *,
                                 sounding_duration_beats: float | None = None) -> dict:
    """Append preparation to a contiguous source grid spanning 0..duration."""
    if not measures or not math.isfinite(duration_beats) or duration_beats <= 0:
        raise ValueError("Practice timeline needs source measures and positive duration")
    previous_end = 0.0
    for measure in measures:
        context = asdict(measure) if is_dataclass(measure) else measure
        try:
            start, end = context["start_beat"], context["end_beat"]
            valid = (math.isfinite(start) and math.isfinite(end)
                     and start == previous_end and end > start)
        except (KeyError, TypeError) as exc:
            raise ValueError("Source measures need explicit finite beat boundaries") from exc
        if not valid:
            raise ValueError("Source measures must form a positive contiguous grid starting at zero")
        previous_end = end
    if previous_end != duration_beats:
        raise ValueError("Source grid must end at the source duration")
    sounding = duration_beats if sounding_duration_beats is None else sounding_duration_beats
    if not math.isfinite(sounding) or sounding < duration_beats:
        raise ValueError("Sounding duration cannot end before the authored grid")
    gap = preparation_measure_descriptor(
        measures[0], sounding, staff_order,
        following_measure=measures[1] if len(measures) > 1 else None)
    return {"schema": SCHEMA, "source_duration_beats": duration_beats,
            "sounding_duration_beats": sounding,
            "stride_beats": gap["end_beat"], "gap": gap}

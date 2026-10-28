"""Per-call source/generated correspondence and exact evidence identity binding.

Each occurrence is consumed at most once. Nonunique identities and report
totals never establish a per-event measurement."""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from math import isfinite
from .visual_contract import source_beat, source_number


def correspondence_key(event, offset=0):
    if event["beat"] is None:
        return None
    clock = event.get("_clock", Fraction(str(event["beat"])))
    return (event["kind"], source_beat(clock - offset), event["staff"],
            tuple(event["spelling"]) if event["kind"] == "note" and event["spelling"] else None)


def measured_records(report):
    measured = report.get("measured", []) if isinstance(report, dict) else []
    return [row for row in measured if isinstance(row, dict)] if isinstance(measured, list) else []


def feature_identity(event):
    return (event["_pixel_id"], event["measure"], event["staff"], event["voice"],
            event["beat"], tuple(event["spelling"]) if event["spelling"] else None)


def feature_record(event, measured, identities):
    identity = feature_identity(event)
    if identities[identity] != 1:
        return None, "Independent XML event identity is not unique"
    matches = []
    for row in measured:
        beat, spelling = row.get("beat"), row.get("spelling")
        if (isinstance(beat, bool) or not isinstance(beat, (int, float)) or not isfinite(beat)
                or isinstance(row.get("measure"), bool)
                or not isinstance(spelling, (list, tuple)) or len(spelling) != 3
                or not isinstance(spelling[0], str)
                or any(type(value) is not int for value in spelling[1:])):
            continue
        key = (row.get("source_id"), source_number(row.get("measure")), row.get("staff"),
               str(row.get("voice")), source_beat(beat), tuple(spelling))
        if key == identity:
            matches.append(row)
    if len(matches) != 1:
        return None, "No unique matching independent per-event feature record"
    return matches[0], ""


def match_generated_events(expected, generated_events, offset=0):
    available = defaultdict(list)
    for path, event in generated_events.items():
        if event["timing_supported"]:
            available[correspondence_key(event)].append(path)
    matched, used_generated = {}, set()
    for path, event in expected.items():
        choices = available.get(correspondence_key(event, offset), [])
        choices = [p for p in choices if p not in used_generated]
        if choices:
            choices.sort(key=lambda p: (generated_events[p]["xml_id"] != event["xml_id"],
                                        generated_events[p]["voice"] != event["voice"]))
            selected = choices[0]
            matched[path] = generated_events[selected]
            used_generated.add(selected)
    return matched, used_generated

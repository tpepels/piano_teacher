"""Bind ordinary pitch/rest records without borrowing missing pixel evidence."""
from __future__ import annotations

from .visual_contract import STATUSES, finite_score, source_beat, source_number
from .visual_rests import rectangular_rest_identified


def pixel_status(event, measured, used):
    candidates = []
    for i, row in enumerate(measured):
        if i in used or row.get("staff") != event["staff"]:
            continue
        if source_number(row.get("measure")) != event["measure"]:
            continue
        try:
            if source_beat(row.get("beat")) != event["beat"]:
                continue
        except (ValueError, TypeError):
            continue
        if str(row.get("voice")) != event["voice"]:
            continue
        if event["kind"] == "note" and row.get("spelling") is not None:
            if list(row["spelling"]) != event["spelling"]:
                continue
        elif event["kind"] == "note":
            continue
        if event["xml_id"] and row.get("source_id") != event["xml_id"]:
            continue
        candidates.append((i, row))
    if not candidates:
        return "unverified", "No matching independent per-event pixel record", None
    if len(candidates) != 1:
        return "ambiguous", "Multiple pixel records cannot establish a unique event identity", None
    i, row = candidates[0]
    used.add(i)
    status = row.get("status")
    if status not in STATUSES:
        return "unverified", "Pixel record has no recognized evidence status", row
    if status != "verified":
        return status, row.get("reason", f"Independent pixel record is {status}"), row
    if event["kind"] == "note":
        expected_glyph = ("head_whole" if event["note_type"] == "whole" else
                          "head_half" if event["note_type"] == "half" else "head_black")
        if row.get("glyph") != expected_glyph or not finite_score(row.get("match")):
            return "unverified", "Pitch record lacks a measured glyph match", row
    else:
        if row.get("required_rest") != event["note_type"]:
            return "unverified", "Rest record does not identify the required written rest", row
        if not finite_score(row.get("shape_match")):
            return "unverified", "Rest record lacks an independently measured contour", row
        if (row.get("type_ambiguity") or (event["note_type"] in {"half", "whole"}
                and not rectangular_rest_identified(row, event["note_type"]))):
            return "ambiguous", "Half/whole rest contour lacks independent staff-grid orientation", row
    return "verified", "Independent raster evidence for pitch position" if event["kind"] == "note" else "Independent isolated rest contour and required grid orientation; voice-lane placement and dots are separate", row

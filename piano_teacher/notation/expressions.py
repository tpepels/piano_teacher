"""Timed, non-assessed source MusicXML expressive marks for native engraving.

Every mark comes from the projected *lesson* MusicXML, never from the
unfiltered imported page. Musical beat positions share the scoring clock,
but these decorations never introduce a graded note or change MIDI timing.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from .lesson import DIVISIONS, LessonScore
from .source_annotations import (
    NATIVE_ARTICULATIONS, NATIVE_DYNAMICS, NATIVE_PEDAL_TYPES,
)


def native_expressions(score: LessonScore, grid: tuple[float, ...]) -> list[dict]:
    root = ET.fromstring(score.musicxml)
    result = []
    for part in root.findall("part"):
        hand = {"RH": "right", "LH": "left"}.get(part.get("id"))
        if hand is None:
            raise ValueError("Unknown lesson hand in expressive score")
        for mi, measure in enumerate(part.findall("measure")):
            if mi + 1 >= len(grid):
                raise ValueError("Expression measure exceeds lesson boundaries")
            cursor = 0
            last_attack = 0
            for child in measure:
                if child.tag in ("backup", "forward"):
                    amount = int(child.findtext("duration"))
                    cursor += amount if child.tag == "forward" else -amount
                    last_attack = cursor
                elif child.tag == "note":
                    if child.find("chord") is None:
                        last_attack = cursor
                    start = last_attack
                    binding = score.note_bindings.get(child.get("id"))
                    if binding is not None and binding.get("is_attack"):
                        for parent in child.findall("notations/articulations"):
                            for mark in parent:
                                if mark.tag in NATIVE_ARTICULATIONS and not mark.attrib:
                                    result.append({
                                        "kind": "articulation", "value": mark.tag,
                                        "hand": hand, "beat": round(
                                            grid[mi] + start / DIVISIONS, 8),
                                        "note_id": child.get("id"),
                                    })
                    if child.find("chord") is None and child.find("grace") is None:
                        cursor += int(child.findtext("duration", "0"))
                elif child.tag == "direction":
                    # Projection places explicit offsets relative to the
                    # measure, before the generated note stream. These never
                    # advance its note/backup cursor.
                    offset = int(child.findtext("offset", str(cursor)))
                    beat = round(grid[mi] + offset / DIVISIONS, 8)
                    if beat < grid[mi] - 1e-7 or beat > grid[mi + 1] + 1e-7:
                        continue
                    for direction_type in child.findall("direction-type"):
                        for kind in direction_type:
                            if kind.tag == "dynamics" and len(kind) == 1:
                                mark = kind[0]
                                if mark.tag in NATIVE_DYNAMICS and not mark.attrib:
                                    result.append({
                                        "kind": "dynamic", "value": mark.tag,
                                        "hand": hand, "beat": beat,
                                    })
                            elif kind.tag == "pedal" and (
                                    kind.get("type") in NATIVE_PEDAL_TYPES):
                                result.append({
                                    "kind": "pedal", "value": kind.get("type"),
                                    "hand": hand, "beat": beat,
                                    "line": kind.get("line", "no") == "yes",
                                    "sign": kind.get("sign", "yes") != "no",
                                })
    return sorted(result, key=lambda mark: (
        mark["beat"], mark["hand"], mark["kind"], mark["value"]))

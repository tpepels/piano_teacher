"""Locate engraved noteheads and rests using Verovio SVG + its quarter-note timemap.

Positions are SVG viewBox-relative. Timing is expressed in *notated quarter beats*,
not wall-clock milliseconds, so practice at 40% and 100% use identical geometry.
No guessed linear page offsets are produced when Verovio supplies no matching notes.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
import re
import xml.etree.ElementTree as ET

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1, 0, 0, 1, 0, 0)
TRANSFORM = re.compile(r"(matrix|translate|scale)\s*\(([^)]*)\)")
NUMBERS = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?")


def _mul(a: Matrix, b: Matrix) -> Matrix:
    aa, ab, ac, ad, ae, af = a
    ba, bb, bc, bd, be, bf = b
    return (aa * ba + ac * bb, ab * ba + ad * bb,
            aa * bc + ac * bd, ab * bc + ad * bd,
            aa * be + ac * bf + ae, ab * be + ad * bf + af)


def _transform(text: str) -> Matrix:
    matrix = IDENTITY
    for item in TRANSFORM.finditer(text):
        numbers = [float(s) for s in NUMBERS.findall(item.group(2))]
        if item.group(1) == "matrix" and len(numbers) == 6:
            op = tuple(numbers)
        elif item.group(1) == "translate" and numbers:
            op = (1, 0, 0, 1, numbers[0], numbers[1] if len(numbers) > 1 else 0)
        elif item.group(1) == "scale" and numbers:
            op = (numbers[0], 0, 0, numbers[1] if len(numbers) > 1 else numbers[0], 0, 0)
        else:
            raise ValueError(f"Unsupported SVG transform: {item.group()}")
        matrix = _mul(matrix, op)  # SVG transform-list ordering
    return matrix


def _apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def _classes(element: ET.Element) -> set[str]:
    return set(element.get("class", "").split())


def _element_position(group: ET.Element, transforms: dict[ET.Element, Matrix]) -> tuple[float, float] | None:
    """A notehead's glyph origin (not its stem, accidental, or decorative glyph)."""
    head = next((e for e in group.iter() if "notehead" in _classes(e)), None)
    candidates = list(head.iter()) if head is not None else list(group.iter())
    for element in candidates:
        if element.tag.rsplit("}", 1)[-1] != "use":
            continue
        try:
            x = float(element.get("x", "0"))
            y = float(element.get("y", "0"))
            return _apply(transforms[element], x, y)
        except (ValueError, KeyError):
            continue
    return None


@dataclass(frozen=True)
class PageGeometry:
    width: float
    height: float
    # id -> (x, y, containing-system-id), in viewBox-relative coordinates
    elements: dict[str, tuple[float, float, str]]


def parse_svg_geometry(svg: str) -> PageGeometry:
    root = ET.fromstring(svg)
    bounds = [float(x) for x in NUMBERS.findall(root.get("viewBox", ""))]
    if len(bounds) != 4 or bounds[2] <= 0 or bounds[3] <= 0:
        raise ValueError("Verovio SVG has no valid viewBox")
    bx, by, width, height = bounds
    matrix: dict[ET.Element, Matrix] = {}
    systems: dict[ET.Element, str] = {}
    found: dict[str, tuple[float, float, str]] = {}

    def walk(node: ET.Element, ancestor: Matrix, system: str):
        transform = _mul(ancestor, _transform(node.get("transform", "")))
        matrix[node] = transform
        if "system" in _classes(node):
            system = node.get("id") or f"system-{len(systems)}"
        systems[node] = system
        for child in node:
            walk(child, transform, system)

    walk(root, IDENTITY, "system-0")
    for elem in root.iter():
        if not (_classes(elem) & {"note", "rest", "mRest", "multiRest"}):
            continue
        identifier = elem.get("id")
        if not identifier:
            continue
        point = _element_position(elem, matrix)
        if point is None:
            continue
        x, y = point
        normalized = ((x - bx) / width, (y - by) / height, systems[elem])
        if not all(math.isfinite(v) for v in normalized[:2]):
            raise ValueError("Non-finite SVG note position")
        found[identifier] = normalized
    return PageGeometry(width, height, found)


def layout_from_pages(svgs: list[str], timemap: list[dict], total_beats: float) -> dict:
    """Return exact note/rest-onset anchors for synchronized, multi-system playback.

    A system is selected by the *next onset* at a wrap. Between onsets in one
    system the playhead interpolates; across a system wrap it jumps instead of
    sweeping backwards over the wrong staff. It holds at the final onset rather
    than inventing coordinates for an unmeasured right barline.
    """
    if total_beats <= 0 or not math.isfinite(total_beats):
        raise ValueError("Invalid exercise duration")
    pages = [parse_svg_geometry(svg) for svg in svgs]
    where: dict[str, tuple[int, float, float, str]] = {}
    for i, page in enumerate(pages):
        for identifier, (x, y, system) in page.elements.items():
            where[identifier] = (i, x, y, system)
    groups = defaultdict(list)
    for event in timemap:
        if "qstamp" not in event:
            continue
        beat = float(event["qstamp"])
        if not (math.isfinite(beat) and -1e-5 <= beat <= total_beats + 1e-5):
            continue
        for identifier in event.get("on", []) + event.get("rests", []):
            if identifier in where:
                page, x, y, system = where[identifier]
                groups[(page, system, round(max(0, beat), 7))].append((x, y))
    if not groups:
        raise ValueError("Verovio supplied no engraved/timed note matches; cannot align playhead")
    # Each staff system is bounded by its own note positions. Even on a page
    # with two systems, the playhead never extends through the wrong one.
    system_y = defaultdict(list)
    for (page, system, _), points in groups.items():
        system_y[(page, system)].extend(y for _, y in points)
    anchors = []
    for (page, system, beat), points in groups.items():
        ys = system_y[(page, system)]
        # bounds are the noteheads +/- a conservative staff height in SVG units
        bottom = max(ys)
        top = min(ys)
        margin = max(0.025, min(0.095, (bottom - top) * 0.45))
        anchors.append({"beat": beat, "page": page,
                        "system": system, "x": sum(x for x, _ in points) / len(points),
                        "top": max(0.0, top - margin), "bottom": min(1.0, bottom + margin)})
    anchors.sort(key=lambda a: (a["beat"], a["page"], a["system"]))
    if any(anchors[i]["beat"] < anchors[i-1]["beat"] for i in range(1,len(anchors))):
        raise AssertionError("Unsorted engraving anchors")
    return {"pages": len(svgs), "beats": total_beats, "anchors": anchors,
            "widths": [p.width for p in pages], "heights": [p.height for p in pages]}


def locate_beat(layout: dict, beat: float) -> dict:
    """Find normalized x/y and page at musical beat. Safe across line wraps."""
    anchors = layout["anchors"]
    if not anchors:
        raise ValueError("No positioned events")
    index = 0
    for i, anchor in enumerate(anchors):
        if anchor["beat"] <= beat + 1e-9:
            index = i
        else:
            break
    left = anchors[index]
    pos = dict(left)
    if index + 1 < len(anchors):
        right = anchors[index + 1]
        if (left["page"], left["system"]) == (right["page"], right["system"]) and right["beat"] > left["beat"]:
            alpha = min(1.0, max(0.0,(beat-left["beat"])/(right["beat"]-left["beat"])))
            pos["x"] = left["x"] + alpha*(right["x"]-left["x"])
    return pos

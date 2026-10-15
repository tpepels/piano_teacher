"""Locate engraved noteheads and rests using Verovio SVG + its quarter-note timemap.

Positions are SVG viewBox-relative. Timing is expressed in *notated quarter beats*,
not wall-clock milliseconds. Tempo can change spacing while preserving beat IDs.
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
    # Rightmost measured barline x for each system (if discoverable).
    system_ends: dict[str, float]
    # Actual staff lines, deduplicated across the measures in each system.
    staff_systems: dict[str, dict]
    # Actual leftmost event ink, including accidentals and staff ledger paths.
    ink_left: dict[str, float]


def parse_svg_geometry(svg: str) -> PageGeometry:
    root = ET.fromstring(svg)
    bounds = [float(x) for x in NUMBERS.findall(root.get("viewBox", ""))]
    if len(bounds) != 4 or bounds[2] <= 0 or bounds[3] <= 0:
        raise ValueError("Verovio SVG has no valid viewBox")
    bx, by, width, height = bounds
    matrix: dict[ET.Element, Matrix] = {}
    systems: dict[ET.Element, str] = {}
    staffs: dict[ET.Element, ET.Element | None] = {}
    found: dict[str, tuple[float, float, str]] = {}
    system_ends: dict[str, float] = {}
    staff_segments = defaultdict(list)
    ledgers = defaultdict(list)

    def walk(node: ET.Element, ancestor: Matrix, system: str,
             viewport: tuple[float, float], staff: ET.Element | None = None):
        transform = _mul(ancestor, _transform(node.get("transform", "")))
        # Verovio uses an outer SVG viewport (e.g. 1056x255) containing a
        # second <svg class="definition-scale" viewBox="0 0 22000 5310">.
        # A nested viewBox maps its local coordinates into the parent's
        # viewport even without a transform attribute. Ignoring that mapping
        # produced x=3.8/y=6.9 normalized noteheads and a blank Godot screen.
        if node is not root and node.tag.rsplit("}", 1)[-1] == "svg":
            nested = [float(v) for v in NUMBERS.findall(node.get("viewBox", ""))]
            if len(nested) == 4 and nested[2] > 0 and nested[3] > 0:
                def dimension(raw: str | None, parent: float) -> float:
                    if not raw:
                        return parent
                    if raw.endswith("%"):
                        return parent * float(raw[:-1]) / 100.0
                    return float(raw)
                local_width = dimension(node.get("width"), viewport[0])
                local_height = dimension(node.get("height"), viewport[1])
                ratio_x = local_width / nested[2]
                ratio_y = local_height / nested[3]
                preserve = node.get("preserveAspectRatio", "xMidYMid meet")
                if preserve.strip() == "none":
                    sx, sy = ratio_x, ratio_y
                    dx, dy = -sx * nested[0], -sy * nested[1]
                else:
                    scale = max(ratio_x, ratio_y) if "slice" in preserve else min(ratio_x, ratio_y)
                    sx = sy = scale
                    dx = (local_width - scale * nested[2]) / 2 - scale * nested[0]
                    dy = (local_height - scale * nested[3]) / 2 - scale * nested[1]
                x_offset = float(node.get("x", "0"))
                y_offset = float(node.get("y", "0"))
                transform = _mul(transform, (sx, 0, 0, sy,
                                             dx + x_offset, dy + y_offset))
                viewport = (nested[2], nested[3])
        matrix[node] = transform
        diagnostic = bool(_classes(node) & {"bounding-box", "content-bounding-box"})
        if "system" in _classes(node) and not diagnostic:
            system = node.get("id") or f"system-{len(systems)}"
        if "staff" in _classes(node) and not diagnostic:
            staff = node
        systems[node] = system
        staffs[node] = staff
        for child in node:
            walk(child, transform, system, viewport, staff)

    walk(root, IDENTITY, "system-0", (width, height))
    for group in root.iter():
        if "ledgerLines" not in _classes(group):
            continue
        for item in group:
            match = re.fullmatch(
                r"\s*M\s*(%s)[,\s]+(%s)\s*L\s*(%s)[,\s]+(%s)\s*"
                % ((NUMBERS.pattern,) * 4), item.get("d", ""))
            if match:
                x1, y1, x2, y2 = map(float, match.groups())
                left, _ = _apply(matrix[item], x1, y1)
                right, _ = _apply(matrix[item], x2, y2)
                ledgers[staffs[group]].append((min(left, right), max(left, right)))
    # Verovio puts each staff's five horizontal paths directly inside a
    # staff group, repeated in every measure. Only inspect those children:
    # descendants also contain note stems, beams and ledger lines.
    for staff in root.iter():
        if "staff" not in _classes(staff):
            continue
        for item in staff:
            tag = item.tag.rsplit("}", 1)[-1]
            segment = None
            if tag == "path":
                match = re.fullmatch(
                    r"\s*M\s*(%s)[,\s]+(%s)\s*L\s*(%s)[,\s]+(%s)\s*"
                    % ((NUMBERS.pattern,) * 4), item.get("d", ""))
                if match:
                    segment = tuple(float(value) for value in match.groups())
            elif tag == "line":
                try:
                    segment = tuple(float(item.get(key, "0")) for key in ("x1", "y1", "x2", "y2"))
                except ValueError:
                    continue
            if segment is None:
                continue
            x1, y1 = _apply(matrix[item], *segment[:2])
            x2, y2 = _apply(matrix[item], *segment[2:])
            if abs(y2 - y1) <= 1e-5 and abs(x2 - x1) > 1e-5:
                staff_segments[systems[staff]].append(
                    ((min(x1, x2)-bx)/width, (max(x1, x2)-bx)/width, (y1-by)/height))
    ink_left = {}
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
        left = x
        # Native content bounds include the actual displaced accidental in a
        # chord; notehead origin alone would erase the pitch instruction.
        for bounds_group in elem:
            if "content-bounding-box" not in _classes(bounds_group):
                continue
            for rect in bounds_group:
                if rect.tag.rsplit("}", 1)[-1] != "rect":
                    continue
                rx, ry = float(rect.get("x", "0")), float(rect.get("y", "0"))
                rw, rh = float(rect.get("width", "0")), float(rect.get("height", "0"))
                if rw > 0 and rh > 0:
                    left = min(left, *(_apply(matrix[rect], cx, cy)[0]
                        for cx, cy in ((rx, ry), (rx+rw, ry), (rx, ry+rh), (rx+rw, ry+rh))))
        for ledger_left, ledger_right in ledgers.get(staffs[elem], []):
            if ledger_left <= x <= ledger_right:
                left = min(left, ledger_left)
        ink_left[identifier] = (left-bx)/width
    # Use only actual Verovio right barlines for terminal held-note timing.
    # Accept SVG lines and absolute move-to paths; unknown glyphs are ignored.
    for elem in root.iter():
        if "barLine" not in _classes(elem):
            continue
        positions = []
        for item in elem.iter():
            tag = item.tag.rsplit("}", 1)[-1]
            try:
                if tag == "line" and item.get("x1") is not None:
                    x = float(item.get("x1"))
                    y = float(item.get("y1", "0"))
                elif tag == "path":
                    match = re.match(r"\s*M\s*(%s)[,\s]+(%s)" % (NUMBERS.pattern, NUMBERS.pattern),
                                     item.get("d", ""))
                    if match is None:
                        continue
                    x, y = float(match.group(1)), float(match.group(2))
                else:
                    continue
                actual_x, _ = _apply(matrix[item], x, y)
                fraction = (actual_x - bx) / width
                if math.isfinite(fraction) and -0.01 <= fraction <= 1.01:
                    positions.append(fraction)
            except (ValueError, KeyError):
                continue
        if positions:
            system = systems[elem]
            system_ends[system] = max(system_ends.get(system, -float("inf")), max(positions))
    staff_systems = {}
    for system, segments in staff_segments.items():
        lines = sorted({round(y, 9) for _, _, y in segments})
        gaps = [b-a for a, b in zip(lines, lines[1:]) if b-a > 1e-7]
        gap = min(gaps) if gaps else .015
        glyph_ys = [y for _, y, containing in found.values() if containing == system]
        # Preserve space for stems, flags and ledger notes. Exact staff lines
        # remain separate so the moving preparation staves can meet them.
        top = min(lines + glyph_ys) - gap * 3
        bottom = max(lines + glyph_ys) + gap * 3
        staff_systems[system] = {
            "left": min(left for left, _, _ in segments),
            "right": max(right for _, right, _ in segments),
            "top": max(0.0, top), "bottom": min(1.0, bottom),
            "staff_lines": lines,
        }
    return PageGeometry(width, height, found, system_ends, staff_systems, ink_left)


def layout_from_pages(svgs: list[str], timemap: list[dict], total_beats: float,
                      pitches: dict[str, int] | None = None) -> dict:
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
    positioned_notes = []
    seen_note_ids = set()
    pitches = pitches or {}
    for event in timemap:
        if "qstamp" not in event:
            continue
        beat = float(event["qstamp"])
        if not (math.isfinite(beat) and -1e-5 <= beat <= total_beats + 1e-5):
            continue
        note_ids = event.get("on", [])
        rest_ids = event.get("restsOn", []) + event.get("rests", [])
        for identifier in note_ids + rest_ids:
            if identifier in where:
                page, x, y, system = where[identifier]
                groups[(page, system, round(max(0, beat), 7))].append(
                    (x, y, identifier in note_ids, pages[page].ink_left[identifier]))
                if identifier in pitches and identifier not in seen_note_ids:
                    positioned_notes.append({"id": identifier, "beat": round(max(0, beat), 7),
                                             "pitch": pitches[identifier], "page": page,
                                             "x": x, "y": y, "system": system})
                    seen_note_ids.add(identifier)
    if not groups:
        raise ValueError("Verovio supplied no engraved/timed note matches; cannot align playhead")
    # Each staff system is bounded by its own note positions. Even on a page
    # with two systems, the playhead never extends through the wrong one.
    system_y = defaultdict(list)
    for (page, system, _), points in groups.items():
        system_y[(page, system)].extend(y for _, y, _, _ in points)
    anchors = []
    for (page, system, beat), points in groups.items():
        ys = system_y[(page, system)]
        # bounds are the noteheads +/- a conservative staff height in SVG units
        bottom = max(ys)
        top = min(ys)
        margin = max(0.025, min(0.095, (bottom - top) * 0.45))
        staff = pages[page].staff_systems.get(system, {})
        # A full-measure rest can be centered in the inactive hand. It must
        # never pull a simultaneous required note away from the timing line.
        note_points = [(x, y) for x, y, is_note, _ in points if is_note]
        timed_points = note_points or [(x, y) for x, y, _, _ in points]
        anchors.append({"beat": beat, "page": page,
                        "system": system, "x": sum(x for x, _ in timed_points) / len(timed_points),
                        "ink_left": min(left for _, _, _, left in points),
                        "top": staff.get("top", max(0.0, top - margin)),
                        "bottom": staff.get("bottom", min(1.0, bottom + margin))})
    anchors.sort(key=lambda a: (a["beat"], a["page"], a["system"]))
    if any(anchors[i]["beat"] < anchors[i-1]["beat"] for i in range(1,len(anchors))):
        raise AssertionError("Unsorted engraving anchors")
    # Continue through a sustained final note only where the actual final
    # barline can be located. Otherwise hold at the final timed glyph.
    last = anchors[-1]
    page = pages[last["page"]]
    boundary = page.system_ends.get(last["system"])
    if (boundary is not None and last["beat"] < total_beats - 1e-7
            and boundary > last["x"] + 1e-5):
        anchors.append({**last, "beat": total_beats, "x": boundary, "terminal": True})
    systems = []
    for page_index, page in enumerate(pages):
        for identifier, bounds in page.staff_systems.items():
            beats = [a["beat"] for a in anchors
                     if a["page"] == page_index and a["system"] == identifier]
            if not beats:
                continue
            next_beats = [a["beat"] for a in anchors if a["beat"] > max(beats)
                          and (a["page"], a["system"]) != (page_index, identifier)]
            systems.append({**bounds, "page": page_index, "system": identifier,
                            "start_beat": min(beats),
                            "end_beat": min(next_beats) if next_beats else total_beats})
    return {"pages": len(svgs), "beats": total_beats, "anchors": anchors, "systems": systems,
            "notes": sorted(positioned_notes, key=lambda n: (n["beat"], n["pitch"], n["id"])),
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

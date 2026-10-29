"""Original SVG structure, inherited source geometry, and subtree isolation.

Reads original transforms, ancestry, glyph IDs/origins and staff/ledger paths.
Asset construction, application layout and raster recognition depend on this
neutral structural layer; none is imported or implemented here.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import copy
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
    # Measured source stem centre, shared by every pitch of a chord.
    stem_x: dict[str, float] = field(default_factory=dict)


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
    stem_x = {}
    parents = {child: parent for parent in root.iter() for child in parent}
    for stem in root.iter():
        classes = _classes(stem)
        if "stem" not in classes or classes & {"bounding-box", "content-bounding-box"}:
            continue
        owner = parents.get(stem)
        while owner is not None and not _classes(owner) & {"note", "chord"}:
            owner = parents.get(owner)
        if owner is None:
            continue
        for path in stem:
            if path.tag.rsplit("}", 1)[-1] != "path":
                continue
            match = re.match(r"\s*M\s*(%s)[,\s]+(%s)" % (NUMBERS.pattern, NUMBERS.pattern),
                             path.get("d", ""))
            if match is None:
                continue
            x, _ = _apply(matrix[path], float(match.group(1)), float(match.group(2)))
            normalized = (x-bx)/width
            if math.isfinite(normalized):
                for note in owner.iter():
                    identifier = note.get("id")
                    if "note" in _classes(note) and identifier in found:
                        stem_x[identifier] = normalized
            break
    return PageGeometry(width, height, found, system_ends, staff_systems, ink_left, stem_x)


def isolate(root: ET.Element, target: ET.Element) -> str:
    """Keep the original XML graphics and inherited transforms/defs."""
    clone = copy.deepcopy(root)
    # Node identity changes on deepcopy: retain the child-index path.
    path=[]
    def locate(node):
        if node is target:
            return True
        for index,child in enumerate(node):
            path.append(index)
            if locate(child):
                return True
            path.pop()
        return False
    if not locate(root):
        raise ValueError("Detached Verovio source node")
    selected=clone
    for index in path:
        selected=selected[index]

    def trim(node):
        if node is selected:
            for el in node.iter():
                for child in list(el):
                    if set(child.get("class","").split()) & {"bounding-box","content-bounding-box"}:
                        el.remove(child)
            return True
        if node.tag.rsplit("}",1)[-1] in {"defs","style"}:
            return True
        yes=False
        for child in list(node):
            if trim(child):
                yes=True
            else:
                node.remove(child)
        return yes
    trim(clone)
    return ET.tostring(clone,encoding="unicode")


__all__ = ("Matrix", "IDENTITY", "TRANSFORM", "NUMBERS", "PageGeometry",
           "parse_svg_geometry", "isolate")

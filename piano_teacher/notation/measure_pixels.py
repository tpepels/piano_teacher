"""Independent measure-width evidence from actual cropped native-canvas PNGs.

Only photographed staff rails/strokes and public beat/clock/density inputs
enter this module. A double/final boundary is anchored at its RIGHTMOST rule;
its preceding rule is typography, not another musical boundary. Repeat dots
are not full-grand-staff strokes and are outside this verifier's claims.

Calibration fits ONE pre-onset clearance for the entire reference frame.
Callers must freeze that returned clearance for subsequent sequence frames;
refitting each image would conceal a common horizontal jump.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from .pixel_proof import detect_staff_lines

GUTTER = 32
PLAYHEAD = .42
_STYLES = {
    "regular": ("thin",), "heavy": ("heavy",),
    "light-light": ("thin", "thin"), "light-heavy": ("thin", "heavy"),
    "heavy-light": ("heavy", "thin"), "heavy-heavy": ("heavy", "heavy"),
}


def detect_barline_strokes(image: Image.Image, *, pixel_scale: float = 1.0) -> dict:
    """Recover solid grand-staff rules; exclude only x < 32 * pixel_scale.

    The foreground contrast mask and .97 complete-column gate retain the
    existing native pixel checks' thresholds, including dim inactive ink.
    Short stems, repeat dots and the horizontal rails cannot satisfy it.
    """
    result = {"passed": False, "errors": [], "staffs": {}, "staff_gap": None,
              "strokes": []}
    if not math.isfinite(pixel_scale) or pixel_scale <= 0:
        result["errors"].append("Public pixel_scale must be positive and finite")
        return result
    gutter = GUTTER*pixel_scale
    try:
        staffs = detect_staff_lines(image)
    except (AssertionError, ValueError) as exc:
        result["errors"].append(f"Staff pixel evidence unavailable: {exc}")
        return result
    result["staffs"] = {hand: {"lines": list(staff.lines), "gap": staff.gap}
                        for hand, staff in staffs.items()}
    result["staff_gap"] = sum(staff.gap for staff in staffs.values()) / len(staffs)
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    background = rgb[0, -1]
    ink = ((rgb[:, :, 0] > background[0] + 42)
           & (rgb[:, :, 1] > background[1] + 32))
    top = round(staffs["right"].lines[0])
    bottom = round(staffs["left"].lines[-1])
    columns = np.flatnonzero(ink[top:bottom+1].mean(axis=0) >= .97)
    groups = []
    for raw in columns:
        col = int(raw)
        if col < gutter:
            continue
        if not groups or col > groups[-1][-1] + 1:
            groups.append([col])
        else:
            groups[-1].append(col)
    for cols in groups:
        result["strokes"].append({
            "center": float(np.mean(cols)), "width": len(cols), "cols": cols,
            "top": top, "bottom": bottom,
            "coverage": float(ink[top:bottom+1, cols].mean())})
    result["passed"] = True
    return result


def _groups(strokes, weights, gap):
    """Solid typographic groups, never grouping an undeclared extra rule.

    Thin/heavy widths have separate staff-relative bands. Paired rules must
    be close but visibly distinct (0.2..0.75 staff spaces, plus raster error).
    Their spacing is measured, not used to move the principal beat anchor.
    """
    count = len(weights)
    for first in range(len(strokes)-count+1):
        selected = strokes[first:first+count]
        if any((stroke["width"] > max(3., .15*gap) if weight == "thin"
                else stroke["width"] < max(3., .20*gap))
               for stroke, weight in zip(selected, weights)):
            continue
        if count == 2:
            separation = selected[1]["center"] - selected[0]["center"]
            if not max(2., .2*gap) <= separation <= .75*gap + 1.5:
                continue
        yield list(range(first, first+count))


def verify_measure_frame(image: Image.Image, boundaries, *, clock_beat: float,
                         density: float, clearance_px: float | None = None,
                         tolerance_px: float = 1.5, pixel_scale: float = 1.0) -> dict:
    """Require a one-to-one visible boundary inventory and invariant widths.

    ``boundaries`` contains independent ``beat``, MusicXML ``style`` (default
    regular) and ``repeat`` (default empty) values. Only solid full-grand-staff
    styles can authorize this proof; partial/dashed/dotted/none fail closed.
    Expected shared source/preparation boundaries must be supplied only once.
    Missing, extra, wrong-style or displaced rules all keep ``passed`` false.
    Widths and position errors are actual pixels, with tolerance <= 1.5px.
    Density and staff measurements are already physical pixels. pixel_scale
    scales ONLY the public fixed system gutter, never geometry or tolerance.
    """
    detected = detect_barline_strokes(image, pixel_scale=pixel_scale)
    result = {**detected, "passed": False, "boundaries": [], "widths": [],
              "clearance_px": clearance_px, "unexpected_strokes": [],
              "clipped_boundaries": []}
    if detected["errors"]:
        return result
    gutter = GUTTER*pixel_scale
    if (not all(math.isfinite(v) for v in (clock_beat, density, tolerance_px))
            or density <= 0 or not 0 <= tolerance_px <= 1.5):
        result["errors"].append("Clock/density must be finite and tolerance must be in [0, 1.5] pixels")
        return result
    gap = detected["staff_gap"]
    if clearance_px is not None and (not math.isfinite(clearance_px)
                                     or not 0 <= clearance_px <= 2*gap):
        result["errors"].append("Shared clearance must be finite and within [0, 2 * measured staff gap]")
        return result
    expected = []
    for boundary in boundaries:
        beat = float(boundary["beat"])
        style = boundary.get("style", "regular")
        repeat = boundary.get("repeat", "")
        if not math.isfinite(beat) or style not in _STYLES or repeat not in ("", "forward", "backward", "both"):
            result["errors"].append(f"Unproved boundary beat/style/repeat: {boundary}")
            continue
        expected.append({"beat": beat, "style": style, "repeat": repeat,
                         "anchor_x": image.width*PLAYHEAD + (beat-clock_beat)*density})
    expected.sort(key=lambda boundary: boundary["beat"])
    if not expected or any(a["beat"] == b["beat"] for a, b in zip(expected, expected[1:])):
        result["errors"].append("Expected boundaries must contain distinct musical beats")
        return result
    strokes = detected["strokes"]
    candidates = {style: list(_groups(strokes, weights, gap)) for style, weights in _STYLES.items()}

    def assign(clearance):
        measured, clipped, errors, used = [], [], [], set()
        previous = -1
        squared_error = 0.
        missing_principals = 0
        for boundary in expected:
            predicted = boundary["anchor_x"] - clearance
            paired = len(_STYLES[boundary["style"]]) == 2
            available = [group for group in candidates[boundary["style"]]
                         if group[0] > previous and not used.intersection(group)]
            nearby = [group for group in available
                      if abs(strokes[group[-1]]["center"]-predicted) <= tolerance_px]
            # An expected group touching an exit cannot authorize a width,
            # but its observed fragments must not become invented extras.
            # At the gutter a complete measured pair wins over this test.
            cut = (predicted <= gutter or predicted >= image.width-1
                   or (paired and not nearby and predicted-(.75*gap+1.5) <= gutter))
            if cut:
                clipped.append(dict(boundary, expected_x=predicted))
                if nearby:
                    group = min(nearby, key=lambda g: abs(strokes[g[-1]]["center"]-predicted))
                    used.update(group)
                elif paired and predicted > gutter and predicted < image.width-1:
                    # Only the principal stroke of a left-clipped pair can
                    # remain. Never exempt another arbitrary nearby rule.
                    principals = [group[0] for group in _groups(
                        strokes, _STYLES[boundary["style"]][-1:], gap)
                        if group[0] > previous and group[0] not in used
                        and abs(strokes[group[0]]["center"]-predicted) <= tolerance_px]
                    if principals:
                        principal = min(principals, key=lambda i: abs(strokes[i]["center"]-predicted))
                        used.add(principal)
                        previous = principal
                    else:
                        errors.append(f"Missing visible principal of {boundary['style']} boundary at beat {boundary['beat']:g}")
                        missing_principals += 1
                continue
            if not available:
                errors.append(f"Missing {boundary['style']} boundary at beat {boundary['beat']:g}")
                continue
            group = min(available, key=lambda g: abs(strokes[g[-1]]["center"]-predicted))
            observed = strokes[group[-1]]["center"]
            used.update(group)
            previous = group[-1]
            error = observed - predicted
            squared_error += error*error
            row = dict(boundary, expected_x=predicted, observed_x=observed,
                       error_px=error, stroke_indices=group,
                       strokes=[strokes[i] for i in group])
            measured.append(row)
            if abs(error) > tolerance_px:
                errors.append(f"Boundary beat {boundary['beat']:g} displaced {error:.3f}px from the shared projection")
        extras = [stroke for i, stroke in enumerate(strokes) if i not in used]
        # A cut stroke at the actual image edge belongs to a declared clipped
        # boundary only when its projected principal rule is at that edge.
        extras = [stroke for stroke in extras if not any(
            abs(stroke["center"]-boundary["expected_x"]) <= tolerance_px
            and (min(stroke["cols"]) == math.ceil(gutter) or max(stroke["cols"]) == image.width-1)
            for boundary in clipped)]
        if extras:
            errors.append(f"Unexpected or duplicate barline strokes: {[s['center'] for s in extras]}")
        missing = len(expected)-len(clipped)-len(measured)
        cost = (missing + missing_principals + len(extras)) * (image.width*len(expected))**2 + squared_error
        return cost, measured, clipped, extras, errors

    if clearance_px is None:
        offsets = {0., 2*gap}
        offsets.update(boundary["anchor_x"]-stroke["center"]
                       for boundary in expected for stroke in strokes
                       if 0 <= boundary["anchor_x"]-stroke["center"] <= 2*gap)
        # Every candidate yields one whole-frame assignment. Fit one least-
        # squares intercept to ALL its assigned principal rules, never one
        # correction per boundary. Inventory penalties prevent hiding extras.
        for offset in tuple(offsets):
            _, rows, _, _, _ = assign(offset)
            if rows:
                fitted = float(np.mean([r["anchor_x"]-r["observed_x"] for r in rows]))
                if 0 <= fitted <= 2*gap:
                    offsets.add(fitted)
        clearance_px = min(sorted(offsets), key=lambda value: assign(value)[0])
    _, measured, clipped, extras, errors = assign(clearance_px)
    result.update(clearance_px=float(clearance_px), boundaries=measured,
                  clipped_boundaries=clipped, unexpected_strokes=extras)
    result["errors"].extend(errors)
    if len(measured) < 2:
        result["errors"].append("Insufficient fully visible boundaries to verify a measure width")
    for left, right in zip(measured, measured[1:]):
        duration = right["beat"] - left["beat"]
        observed = right["observed_x"] - left["observed_x"]
        expected_width = duration*density
        error = observed-expected_width
        result["widths"].append({"start_beat": left["beat"], "end_beat": right["beat"],
            "duration_beats": duration, "expected_px": expected_width,
            "observed_px": observed, "error_px": error, "passed": abs(error) <= tolerance_px})
        if abs(error) > tolerance_px:
            result["errors"].append(f"Measure {left['beat']:g}..{right['beat']:g} width {observed:.3f}px; expected {expected_width:.3f}px")
    result["passed"] = not result["errors"]
    return result

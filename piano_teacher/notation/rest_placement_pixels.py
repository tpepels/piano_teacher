"""Readable rest-grid placement from independent contour and clearance evidence.

This policy reads registered font origins and suppressed-frame ink. It does
not infer the authored voice lane, source timing, or global extra-ink absence."""
from __future__ import annotations

import math
from .rest_contours import rest_placement_registration


def rest_clearance(silhouette, other_ink, gap: float) -> tuple[float, bool]:
    """Conservative pixel-edge clearance, bounded to one staff space.

    Eight-neighbor dilation measures Chebyshev distance, a lower bound on
    Euclidean clearance. Adjacent pixel squares touch and have zero clearance.
    A capped result states a lower bound, never infinite clearance.
    """
    import numpy as np

    grown = silhouette.copy()
    limit = math.ceil(gap)+1
    for distance in range(limit+1):
        if np.any(grown & other_ink):
            return float(max(0, distance-1)), False
        padded = np.pad(grown, 1)
        grown = np.logical_or.reduce([
            padded[dy:dy+grown.shape[0], dx:dx+grown.shape[1]]
            for dy in range(3) for dx in range(3)])
    return float(limit-1), True


def rest_placement_evidence(body: dict, glyph: dict, delta, suppressed_ink,
                             staves: dict, staff_name: str, *, note_type: str) -> dict:
    """Prove a readable grid-relative layout, never an intended voice lane."""
    import numpy as np

    staff = staves[staff_name]
    gap, center = staff.gap, staff.lines[2]
    ys, xs = np.nonzero(delta)
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    required_clearance = .12
    # Two and a half spaces beyond the printed rails, clipped at the midpoint
    # to an adjacent staff. This is an explicit readability bound, not a
    # source-derived declaration of the intended rest voice or lane.
    top, bottom = max(0., staff.lines[0]-2.5*gap), min(delta.shape[0]-1., staff.lines[-1]+2.5*gap)
    for name, other in staves.items():
        if name == staff_name:
            continue
        midpoint = (other.lines[2]+center)/2
        if other.lines[2] < center:
            top = max(top, midpoint+required_clearance*gap)
        else:
            bottom = min(bottom, midpoint-required_clearance*gap)
    evidence = dict(status="unverified", bbox=bbox, body_bbox=body["box"],
                    staff_lines=list(staff.lines), staff_gap=gap,
                    corridor_y=[top, bottom], required_clearance_spaces=required_clearance,
                    grid_phase_tolerance_spaces=.13)
    registered = rest_placement_registration(body, glyph, gap)
    evidence["registration_match"] = round(registered["match"], 4)
    if registered["match"] < .79:
        return dict(evidence, reason="Rest contour cannot independently establish a bounded font-origin registration")
    registrations = registered["registrations"]
    best = max(registrations, key=lambda c: c["score"])
    baseline = best["baseline_y"]
    offsets = [(c["baseline_y"]-center)/gap for c in registrations]
    # Rectangular rests must preserve hanging/sitting phase. Other native
    # rest glyphs can occupy either a line or space in a readable voice lane.
    grid_step = 1. if note_type in {"whole", "half"} else .5
    errors = [abs(offset-round(offset/grid_step)*grid_step) for offset in offsets]
    evidence.update(baseline_y=baseline, relative_offset_spaces=round((baseline-center)/gap, 4),
                    baseline_range_y=[min(c["baseline_y"] for c in registrations),
                                      max(c["baseline_y"] for c in registrations)],
                    grid_phase_error_spaces=round(max(errors), 4))

    # Reconstruct the full external body, including ink hidden beneath another
    # symbol. Visible subtraction alone could miss same-colored overlapping
    # ink. Dots additionally contribute their actual isolated removed pixels.
    template = registered["template"]
    left = min(bbox[0], min(c["x"] for c in registrations))
    right = max(bbox[2], max(c["x"]+template.shape[1]-1 for c in registrations))
    upper = min(bbox[1], min(c["y"] for c in registrations))
    lower = max(bbox[3], max(c["y"]+template.shape[0]-1 for c in registrations))
    evidence["silhouette_bbox"] = [left, upper, right, lower]
    if left < 0 or upper < 0 or right >= delta.shape[1] or lower >= delta.shape[0]:
        return dict(evidence, reason="Complete external rest outline is clipped by the framebuffer")
    pad = math.ceil(gap)+1
    x0, y0 = max(0, left-pad), max(0, upper-pad)
    x1, y1 = min(delta.shape[1], right+pad+1), min(delta.shape[0], lower+pad+1)
    silhouette = delta[y0:y1, x0:x1].copy()
    for c in registrations:
        y, x = c["y"]-y0, c["x"]-x0
        silhouette[y:y+template.shape[0], x:x+template.shape[1]] |= template
    clearance, capped = rest_clearance(silhouette, suppressed_ink[y0:y1, x0:x1], gap)
    evidence.update(min_clearance_pixels=clearance, min_clearance_spaces=round(clearance/gap, 4),
                    clearance_capped=capped, clearance_search_spaces=1.)
    if clearance/gap < required_clearance:
        return dict(evidence, status="mismatch", reason="Other bright framebuffer ink touches, overlaps or crowds the rest/dot silhouette")
    if upper-.5 < top or lower+.5 > bottom:
        return dict(evidence, status="mismatch", reason="Rest/dot silhouette lies outside its readable staff corridor")
    if max(errors) > .13:
        return dict(evidence, status="mismatch" if min(errors) > .2 else "ambiguous",
                    reason="Independent font-origin registration does not establish the rest type's staff-grid phase")
    return dict(evidence, status="verified", reason="External-font baseline follows the staff grid inside a readable corridor with independent bright-ink clearance")

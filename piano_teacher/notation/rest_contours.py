"""Authentic rest/body/dot contours and bounded raster registration.

The external-font mask caches and every per-intervention changed-pixel claim
retain their existing thresholds. A body flag bulb cannot become a source dot."""
from __future__ import annotations

import math
from PIL import Image
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=128)
def render_rest_outline(svg: str, width: int, height: int):
    """Cache identical authentic font masks across thousands of full-score rests."""
    from io import BytesIO
    import cairosvg
    import numpy as np

    png=cairosvg.svg2png(bytestring=svg.encode(),
                         output_width=width,output_height=height)
    alpha=np.asarray(Image.open(BytesIO(png)).convert("RGBA"))[:,:,3]
    return alpha >= 80


def rest_template_mask(glyph: dict, gap: float):
    """Rasterize the original Verovio SVG at the *measured image* staff scale."""
    bounds=glyph["bounds"]
    width=max(1,round(float(bounds[2])*gap/250))
    height=max(1,round(float(bounds[3])*gap/250))
    return render_rest_outline(glyph["svg"],width,height)


def compare_isolated_masks(observed, reference) -> float:
    """Compare two binary rest glyphs up to two pixels of raster registration.

    Unlike the old raw-image classifier, *no nearby stem, note or different
    rest is visible* in the controlled difference mask. The vertical lane is
    read from pixels, not taken from the renderer's rest-y diagnostic.
    """
    import numpy as np

    ys,xs=np.nonzero(observed)
    ry,rx=np.nonzero(reference)
    if len(xs)<5 or len(rx)<5:
        return 0.0
    # Trim SVG's standard transparent 12-unit margin; neither template
    # nor rendered image is resized to force a match.
    data=observed[ys.min():ys.max()+1,xs.min():xs.max()+1]
    shape=reference[ry.min():ry.max()+1,rx.min():rx.max()+1]
    h=max(data.shape[0],shape.shape[0])+8
    w=max(data.shape[1],shape.shape[1])+8
    best=0.0
    for dy in range(-2,3):
        for dx in range(-2,3):
            left=4+dx
            top=4+dy
            canvas=np.zeros((h,w),dtype=bool)
            canvas[top:top+shape.shape[0],left:left+shape.shape[1]]=shape
            test=np.zeros((h,w),dtype=bool)
            test[4:4+data.shape[0],4:4+data.shape[1]]=data
            intersect=int(np.count_nonzero(canvas & test))
            dice=2*intersect/(int(canvas.sum())+int(test.sum()))
            if dice>best:
                best=dice
    return best


def rest_delta_parts(delta, gap: float) -> list[dict]:
    """Separate horizontally detached marks; bridge only small raster gaps.

    A playhead can occlude a narrow column through a rest. Joining that cut
    does not authorize joining a detached dot to the body. Inseparable ink
    stays in one part and cannot establish independent dot ownership.
    """
    import numpy as np

    columns = np.flatnonzero(delta.any(axis=0))
    groups = []
    for x in columns:
        if not groups or x-groups[-1][-1]-1 > max(1, math.floor(.12*gap)):
            groups.append([])
        groups[-1].append(int(x))
    parts = []
    for group in groups:
        left, right = group[0], group[-1]
        rows = np.flatnonzero(delta[:, left:right+1].any(axis=1))
        top, bottom = int(rows[0]), int(rows[-1])
        mask = delta[top:bottom+1, left:right+1]
        parts.append(dict(mask=mask, box=[left, top, right, bottom]))
    return sorted(parts, key=lambda part: int(part["mask"].sum()), reverse=True)


@lru_cache(maxsize=32)
def rest_dot_template_mask(gap: float):
    """Read SMuFL augmentation-dot ink from the external Leipzig font."""
    from xml.etree import ElementTree as ET
    import verovio

    resources = Path(verovio.__file__).resolve().parent / "data"
    metric = ET.parse(resources/"Leipzig.xml").getroot().find("g[@c='E1E7']")
    if metric is None:
        raise ValueError("External font lacks an augmentation-dot metric")
    x, y, w, h = (float(metric.get(k)) for k in ("x", "y", "w", "h"))
    bounds = [x-12, -y-h-12, w+24, h+24]
    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
                     viewBox=" ".join(map(str, bounds)), fill="white")
    svg.append(ET.parse(resources/"Leipzig/E1E7.xml").getroot())
    return rest_template_mask(dict(svg=ET.tostring(svg, encoding="unicode"),
                                    bounds=bounds), gap)


def rest_dot_components(parts: list[dict]) -> list[dict]:
    """Recover actual detached contours inside column-grouped changed ink.

    Body grouping tolerates narrow raster/playhead cuts. That tolerance must
    not merge nearby dot circles: only eight-connected original changed
    pixels belong to one mark. Every input pixel remains in exactly one part.
    """
    import numpy as np

    components = []
    for part in parts:
        remaining = set(zip(*np.nonzero(part["mask"])))
        while remaining:
            first = remaining.pop()
            pending, seen = [first], {first}
            while pending:
                y, x = pending.pop()
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        neighbor = (y+dy, x+dx)
                        if neighbor in remaining:
                            remaining.remove(neighbor)
                            seen.add(neighbor)
                            pending.append(neighbor)
            ys, xs = zip(*seen)
            left, top, right, bottom = map(int, (min(xs), min(ys), max(xs), max(ys)))
            mask = np.zeros((bottom-top+1, right-left+1), dtype=bool)
            for y, x in seen:
                mask[y-top, x-left] = True
            components.append(dict(part, mask=mask, box=[part["box"][0]+left,
                part["box"][1]+top, part["box"][0]+right, part["box"][1]+bottom]))
    return components


def rest_dot_evidence(parts: list[dict], body_box: list[int],
                       count: int, gap: float, *, visible_removed) -> dict:
    """Require distinct, detached, rightward dot contours in removed ink.

    No unchanged neighbor or control-only addition can supply a dot, and no
    changed part is ignored. Each actual removed pale contour independently
    passes the same external-font threshold as its full changed contour.
    Touching/occluded dots and more than three dots remain nonverified.
    """
    evidence = dict(status="unverified", expected_count=count,
                    observed_count=0, dots=[])
    if count > 3:
        return dict(evidence, status="unsupported", reason="More than three rest dots needs separate bounded assignment")
    if not parts and not count:
        return dict(evidence, status="verified", reason="No detached changed ink or written dots")
    reference = rest_dot_template_mask(gap)
    previous = None
    for part in sorted(rest_dot_components(parts), key=lambda p: p["box"][0]):
        box = part["box"]
        x, y = (box[0]+box[2])/2, (box[1]+box[3])/2
        match = compare_isolated_masks(part["mask"], reference)
        right = part.get("body_right_at_dot", body_box[2])
        separated = (.1*gap <= box[0]-right <= 2.2*gap and
                     body_box[1]-.75*gap <= y <= body_box[3]+.75*gap)
        if previous is not None:
            separated = separated and .4*gap <= x-previous[0] <= .9*gap and abs(y-previous[1]) <= .15*gap
        if match < .8 or not separated:
            return dict(evidence, reason="Detached changed ink cannot establish separate rest-dot contours")
        x0,y0,x1,y1 = box
        removed = part["mask"] & visible_removed[y0:y1+1,x0:x1+1]
        removed_match = compare_isolated_masks(removed, reference)
        if removed_match < .8:
            return dict(evidence, visible_removed_match=round(removed_match, 4),
                        reason="Dot lacks an independently matching removed visible pale contour")
        dot = dict(box=box, shape_match=round(match, 4),
                   visible_removed_match=round(removed_match, 4))
        if "body_reference_match" in part:
            dot.update(body_reference_match=part["body_reference_match"],
                       body_right_at_dot=right)
        evidence["dots"].append(dot)
        evidence["observed_count"] += 1
        previous = x, y
    if evidence["observed_count"] != count:
        return dict(evidence, status="mismatch" if evidence["observed_count"] > count else "unverified",
                    reason="Observed isolated rest-dot count differs from written count")
    return dict(evidence, status="verified", reason="Every written rest dot has distinct suppressed external-font ink")


def rest_placement_registration(body: dict, glyph: dict, gap: float) -> dict:
    """Register external ink without resizing it or choosing a staff lane.

    Retain every near-best raster registration. All of their independently
    inferred font origins must support the same staff-grid phase.
    """
    import numpy as np

    raw = rest_template_mask(glyph, gap)
    ys, xs = np.nonzero(raw)
    template = raw[ys.min():ys.max()+1, xs.min():xs.max()+1]
    observed = body["mask"]
    h, w = max(observed.shape[0], template.shape[0])+8, max(observed.shape[1], template.shape[1])+8
    ink = np.zeros((h, w), dtype=bool)
    ink[4:4+observed.shape[0], 4:4+observed.shape[1]] = observed
    denominator = int(ink.sum())+int(template.sum())
    candidates = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            expected = np.zeros((h, w), dtype=bool)
            expected[4+dy:4+dy+template.shape[0], 4+dx:4+dx+template.shape[1]] = template
            score = 2*int((ink & expected).sum())/denominator
            candidates.append(dict(score=score, x=body["box"][0]+dx, y=body["box"][1]+dy))
    best = max(c["score"] for c in candidates)
    registrations = [c for c in candidates if c["score"] >= best-.02]
    for c in registrations:
        c["baseline_y"] = c["y"]-int(ys.min())-float(glyph["bounds"][1])*gap/250
    return dict(match=best, template=template, registrations=registrations)


def partition_rest_body_dots(body: dict, marks: list[dict], glyph: dict,
                             gap: float, count: int) -> tuple[dict, list[dict]]:
    """Separate a detached dot sharing the body's horizontal projection.

    A short rest has dot-like flag bulbs of its own. No bulb owned by ANY
    near-best independently registered font body can become an augmentation
    dot. Removing candidate dots must leave a .79 authentic body, then each
    dot must be detached and rightward of that body's ink at the dot's Y.
    """
    import numpy as np

    if not 0 < count <= 3:
        return body, marks
    reference = rest_dot_template_mask(gap)
    candidates = [part for part in rest_dot_components([body])
                  if compare_isolated_masks(part["mask"], reference) >= .8]
    if not candidates:
        return body, marks

    def footprint(registered):
        ys, xs = np.nonzero(registered["template"])
        return set().union(*(set(zip(ys+c["y"], xs+c["x"]))
                             for c in registered["registrations"]))

    registered = rest_placement_registration(body, glyph, gap)
    if registered["match"] < .65:
        return body, marks
    owned = footprint(registered)
    detached = []
    for part in candidates:
        ys, xs = np.nonzero(part["mask"])
        support = set(zip(ys+part["box"][1], xs+part["box"][0]))
        if not owned.intersection(support):
            detached.append((part, support))
    if not detached:
        return body, marks
    remaining = body["mask"].copy()
    for _, support in detached:
        for y, x in support:
            remaining[y-body["box"][1], x-body["box"][0]] = False
    ys, xs = np.nonzero(remaining)
    if len(xs) < 12:
        return body, marks
    left, top, right, bottom = map(int, (xs.min(), ys.min(), xs.max(), ys.max()))
    clean = dict(mask=remaining[top:bottom+1,left:right+1],
                 box=[body["box"][0]+left,body["box"][1]+top,
                      body["box"][0]+right,body["box"][1]+bottom])
    registered = rest_placement_registration(clean, glyph, gap)
    if registered["match"] < .79:
        return body, marks
    owned = footprint(registered)
    extracted = []
    for part, support in detached:
        box = part["box"]
        band = [x for y, x in owned if box[1] <= y <= box[3]]
        if not band or owned.intersection(support):
            return body, marks
        body_right = int(max(band))
        if not .1*gap <= box[0]-body_right <= 2.2*gap:
            return body, marks
        extracted.append(dict(part,body_right_at_dot=body_right,
                              body_reference_match=round(registered["match"],4)))
    return clean, marks+extracted

"""Bounded external-font family measurements and detached contour ownership.

Support sets are temporary physical-ink claims, consumed by callers within a
single frame. No feature coordinator or renderer data authorizes a match.
"""
from .feature_contract import GLYPH_MINIMUM, FAMILY_MARGIN, feature_result
from .raster_matching import match_glyph, _joint_candidates


def _locate(pixels, glyph, gap, x, y, dxs, dys, *, centered=True):
    b = glyph['bounds']
    if not centered:
        x += (b[0] + b[2]/2)*gap/250
    score = match_glyph(pixels, glyph, gap, x, y, centered=True, dxs=dxs, dys=dys)
    if score < GLYPH_MINIMUM:
        return score, None
    request = dict(glyph=glyph, gap=gap, origin_y=y, dxs=dxs, dys=dys)
    candidates = _joint_candidates(pixels, request, x, dys, GLYPH_MINIMUM)
    row = candidates[0] if candidates else None
    if row is not None:
        row['bbox'] = [row['x'], row['y'], row['x']+max(1, round(b[2]*gap/250)),
                       row['y']+max(1, round(b[3]*gap/250))]
    return score, row


def closed_component(pixels, row):
    """All ink used by a detached glyph must end inside its own mask box.

    A small dot/flat mask cannot claim a subset of a neighboring notehead,
    stem or tie. Include all connected observed ink, including antialiasing
    pixels outside the expected outline, in the ownership claim.
    """
    x0, y0, x1, y1 = row['bbox']
    width = pixels.shape[1]
    pending = list(row['support'])
    visited = set(pending)
    while pending:
        index = pending.pop()
        y, x = divmod(index, width)
        if not (x0 <= x < x1 and y0 <= y < y1):
            return None
        for yy in range(max(0, y-1), min(pixels.shape[0], y+2)):
            for xx in range(max(0, x-1), min(width, x+2)):
                key = yy*width + xx
                if pixels[yy, xx] and key not in visited:
                    visited.add(key)
                    pending.append(key)
    return frozenset(visited)


def measure_glyph_family(pixels, glyphs, names, expected, gap, x, y, dxs, dys, *, detached=False, centered=True,
            y_offsets=None):
    if expected not in glyphs or any(name not in glyphs for name in names):
        return feature_result('unsupported', 'External font lacks a required family outline', expected=expected)
    ranked = []
    for name in names:
        origin_y = y+(y_offsets or {}).get(name, 0)
        score, row = _locate(pixels, glyphs[name], gap, x, origin_y, dxs, dys, centered=centered)
        ranked.append((score, name, row))
    ranked.sort(key=lambda entry: -entry[0])
    score, name, row = ranked[0]
    runner = ranked[1][0] if len(ranked) > 1 else 0.
    evidence = dict(expected=expected, observed=name, score=round(score, 4),
                    runner_up=round(runner, 4), margin=round(score-runner, 4))
    if score < GLYPH_MINIMUM:
        return feature_result('unverified', 'Insufficient authentic glyph contour at the bound feature position', **evidence)
    if name != expected:
        return feature_result('mismatch', 'A different authentic glyph family member has the strongest contour', **evidence)
    if score-runner < FAMILY_MARGIN:
        return feature_result('ambiguous', 'Authentic glyph family margin is below .05', **evidence)
    support = closed_component(pixels, row) if detached else row['support']
    if support is None:
        return feature_result('ambiguous', 'Feature contour is connected to neighboring ink outside its own box', **evidence)
    result = feature_result('verified', 'Authentic external glyph passes .72 Dice and .05 family margin',
                     **evidence, bbox=row['bbox'])
    result['_support'] = support
    return result

"""Bounded unexpected-ink observations on actual, uniformly sampled PNGs.

This is deliberately a fail-closed extension of the existing pixel probes,
not a whole-score correctness verdict. External Leipzig outlines are scanned
BEFORE source ownership. Inactive ink is included. Source identities attach
only at photographed source onsets; image translation tracks that same ink.
Unclassified pixels, clipped/occluded glyphs and ambiguous tracking remain
unknown. No renderer coordinates, density, atlas or RGB telemetry are read.

Finite snapshots cannot exclude between-frame transients or raster-identical
overprinting. Exact rail-colored ink is likewise not separable from a rail.
"""
from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from functools import lru_cache
import math
from pathlib import Path

import numpy as np
from PIL import Image

from .connector_pixels import _translation
from .feature_pixels import _closed_component, _feature_glyphs, _register
from .phase3_pixels import _clef_at, _rectangular_rest_orientation
from .pixel_proof import detect_staff_lines, expected_y
from .proof import read_written_score
from .symbol_pixel_proof import _outline

STRIPE_HALF_WIDTH = 64
MAX_CLOCK_STEP = .15
MAX_POSITION_ERROR = 3.
MAX_CANDIDATES = 256
MAX_FRAME_PIXELS = 2_000_000
TEMPLATE_FFT_CACHE_BYTES = 224*1024**2
_SPECTRA = OrderedDict()


def _family(name):
    return name.split('_')[0] if name != 'augmentation_dot' else 'dot'


@lru_cache(maxsize=128)
def _template(name, gap):
    glyph = _feature_glyphs()[name]
    bounds = glyph['bounds']
    return _outline(glyph['svg'], max(1, round(bounds[2]*gap/250)),
                    max(1, round(bounds[3]*gap/250)))


def _spectrum(name, gap, shape):
    key = name, gap, shape
    if key in _SPECTRA:
        _SPECTRA.move_to_end(key)
        return _SPECTRA[key]
    template = _template(name, gap)
    result = np.fft.rfft2(template[::-1, ::-1].astype(np.float32), s=shape)
    # Large endcap-only transforms must not evict the ordinary stripe/tile
    # kernels reused by thousands of frames. Cache only authentic templates.
    if shape[0]*shape[1] <= 1024**2 and result.nbytes <= TEMPLATE_FFT_CACHE_BYTES:
        while _SPECTRA and sum(s.nbytes for s in _SPECTRA.values())+result.nbytes > TEMPLATE_FFT_CACHE_BYTES:
            _SPECTRA.popitem(last=False)
        _SPECTRA[key] = result
    return result


def _modal_rule_row(rgb):
    row = rgb.astype(np.uint32)
    packed = (row[:, 0] << 16) | (row[:, 1] << 8) | row[:, 2]
    colors, counts = np.unique(packed, return_counts=True)
    return packed == colors[np.argmax(counts)] if counts.max() > len(row)*.4 else np.zeros(len(row), bool)


def _photo(path):
    with Image.open(path) as raw:
        image = raw.convert('RGB')
    if image.width*image.height > MAX_FRAME_PIXELS:
        raise ValueError('Framebuffer exceeds bounded pixel budget')
    rgb = np.asarray(image).astype(np.int16)
    staves = detect_staff_lines(image)
    # Per-column background accommodates the photographed playhead glow.
    background = np.median(rgb, axis=0)
    contrast = np.min(rgb-background[None, :, :], axis=2)
    colored = ((rgb[:, :, 1]-rgb[:, :, 0] > 30)
               & (rgb[:, :, 2]-rgb[:, :, 0] > 15))
    raw_ink = (contrast > 4) & ~colored
    layers = [(contrast > level) & ~colored for level in (20, 100)]
    # Remove only actual modal rule COLORS at independently detected rails,
    # never entire horizontal rows. Brighter glyph intersections survive.
    rails = np.zeros(raw_ink.shape, dtype=bool)
    for staff in staves.values():
        for line in staff.lines:
            for y in range(max(0, math.floor(line)-2), min(image.height, math.ceil(line)+3)):
                rails[y] = _modal_rule_row(rgb[y])
    ink = raw_ink & ~rails
    layers = [mask & ~rails for mask in layers]
    columns = np.flatnonzero(colored.sum(axis=0) > image.height*.35)
    camera = float(np.mean(columns)) if len(columns) in (1, 2, 3, 4) else None
    return dict(ink=ink, layers=layers, staves=staves, camera=camera,
                occlusion=colored, occlusion_columns=columns,
                occluded=int(colored.sum()), shape=ink.shape)


def _scores(pixels, template, transforms=None, integral=None, kernel_key=None):
    """All translations of one authentic silhouette, without window copies."""
    h, w = template.shape
    H, W = pixels.shape
    if h > H or w > W:
        return np.empty((0, 0))
    shape = (1 << (H+h-2).bit_length(), 1 << (W+w-2).bit_length())
    transforms = {} if transforms is None else transforms
    if shape not in transforms:
        transforms[shape] = np.fft.rfft2(pixels.astype(np.float32), s=shape)
    kernel = (_spectrum(*kernel_key, shape) if kernel_key else
              np.fft.rfft2(template[::-1, ::-1].astype(np.float32), s=shape))
    product = transforms[shape]*kernel
    intersection = np.fft.irfft2(product, s=shape)[h-1:H, w-1:W]
    if integral is None:
        integral = np.pad(pixels.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    count = integral[h:, w:]-integral[:-h, w:]-integral[h:, :-w]+integral[:-h, :-w]
    # Correlation counts are integers. Recover the exact counts after FFT
    # roundoff, retaining the original mathematical Dice thresholds.
    return 2*np.rint(np.maximum(intersection, 0))/(count+int(template.sum())+1e-9)


def _overlap(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0, x1-x0)*max(0, y1-y0)


def _search_crop(layers, template, minimum, bounds=None):
    """Discard only translations mathematically unable to pass original Dice.

    Dice >= d requires intersection >= d*N/(2-d), since observed ink is at
    least the intersection. Bound that intersection by the actual foreground
    extent and authentic template row/column masses. No density assumption,
    arbitrary area cutoff or changed threshold enters this pruning.
    """
    H, W = layers[0].shape
    h, w = template.shape
    if h > H or w > W:
        return None
    if bounds is None:
        ys = np.flatnonzero(np.logical_or.reduce([a.any(axis=1) for a in layers]))
        xs = np.flatnonzero(np.logical_or.reduce([a.any(axis=0) for a in layers]))
        if not len(xs) or not len(ys):
            return None
        bounds = (int(xs[0]), int(ys[0]), int(xs[-1])+1, int(ys[-1])+1)
    needed = math.ceil(minimum*int(template.sum())/(2-minimum)-1e-9)
    ranges = []
    for size, length, first, last, mass in (
            (H, h, bounds[1], bounds[3], template.sum(axis=1)),
            (W, w, bounds[0], bounds[2], template.sum(axis=0))):
        starts = np.arange(size-length+1)
        cumulative = np.r_[0, mass.cumsum()]
        upper = np.clip(last-starts, 0, length)
        lower = np.clip(first-starts, 0, length)
        feasible = np.flatnonzero(cumulative[upper]-cumulative[lower] >= needed)
        if not len(feasible):
            return None
        ranges.append((int(feasible[0]), int(feasible[-1])+length))
    return [ranges[1][0], ranges[0][0], ranges[1][1], ranges[0][1]]


def _scan(photo, areas, controls=None):
    """Source-independent family search on original ink, before any claims.

    Areas choose computation only. Both complete endcaps are searched; other
    frames include the stripe and every novel-ink tile, wherever it occurs.
    """
    names = [n for n in _feature_glyphs() if n.startswith(('head_', 'rest_', 'flag_'))
             or n == 'augmentation_dot' or (n.startswith(('clef_', 'time_'))
                                            and (controls is None or n in controls))]
    gap = round(min(s.gap for s in photo['staves'].values()), 3)
    found = []
    for left, top, right, bottom in areas:
        original = [layer[top:bottom, left:right] for layer in photo['layers']]
        ys = np.flatnonzero(np.logical_or.reduce([a.any(axis=1) for a in original]))
        xs = np.flatnonzero(np.logical_or.reduce([a.any(axis=0) for a in original]))
        if not len(xs) or not len(ys):
            continue
        bounds = (int(xs[0]), int(ys[0]), int(xs[-1])+1, int(ys[-1])+1)
        buckets = defaultdict(list)
        for name in names:
            template = _template(name, gap)
            threshold = .90 if name == 'augmentation_dot' else .79
            crop = _search_crop(original, template, threshold, bounds)
            if crop is None:
                continue
            buckets[1 << (template.shape[0]-1).bit_length()].append((name, template, threshold, crop))
        for tasks in buckets.values():
            # A shared enclosing crop preserves EVERY feasible translation
            # while reusing input FFTs/integrals across similarly sized glyphs.
            xa = min(task[3][0] for task in tasks)
            ya = min(task[3][1] for task in tasks)
            xb = max(task[3][2] for task in tasks)
            yb = max(task[3][3] for task in tasks)
            regions = [layer[ya:yb, xa:xb] for layer in original]
            integrals = [np.pad(layer.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
                         for layer in regions]
            transforms = [{}, {}]
            for name, template, threshold, _crop in tasks:
                h, w = template.shape
                best = None
                for layer, transform, integral in zip(regions, transforms, integrals):
                    scores = _scores(layer, template, transform, integral, (name, gap))
                    best = scores if best is None else np.maximum(best, scores)
                maxima = best >= threshold
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    maxima &= best >= np.roll(best, (dy, dx), axis=(0, 1))
                for y, x in np.argwhere(maxima):
                    box = [int(x+left+xa), int(y+top+ya),
                           int(x+left+xa+w), int(y+top+ya+h)]
                    if name == 'augmentation_dot':
                        x0, y0, x1, y1 = box
                        ring = photo['layers'][0][max(0, y0-1):y1+1, max(0, x0-1):x1+1].copy()
                        ring[y0-max(0, y0-1):y1-max(0, y0-1), x0-max(0, x0-1):x1-max(0, x0-1)] = False
                        if ring.any():
                            continue
                    found.append(dict(name=name, family=_family(name), bbox=box,
                                      score=round(float(best[y, x]), 5), gap=gap))
    # Suppress only alternate raster phases of the SAME family. Different
    # families are kept for ambiguity checks before any ownership masking.
    selected = []
    for row in sorted(found, key=lambda r: -r['score']):
        a = row['bbox']
        if any(row['family'] == b['family'] and _overlap(a, b['bbox']) >
               .65*min((a[2]-a[0])*(a[3]-a[1]),
                       (b['bbox'][2]-b['bbox'][0])*(b['bbox'][3]-b['bbox'][1])) for b in selected):
            continue
        selected.append(row)
        if len(selected) > MAX_CANDIDATES:
            raise ValueError('Family candidate budget exceeded; no absence claim')
    return selected


def _shifted(mask, shift):
    result = np.zeros_like(mask)
    lo, hi = max(0, -shift), min(mask.shape[1], mask.shape[1]-shift)
    if lo < hi:
        result[:, lo+shift:hi+shift] = mask[:, lo:hi]
    return result


def _motion(previous, current, dt, source_objects=()):
    if previous['shape'] != current['shape']:
        raise ValueError('Framebuffer dimensions changed')
    for hand, staff in previous['staves'].items():
        if max(abs(a-b) for a, b in zip(staff.lines, current['staves'][hand].lines)) > 1:
            raise ValueError('Photographed staff rails changed')
    # Pale and dim layers may have different antialiasing. Either must pass
    # the existing strict .80 / .04 unique-photo registration; disagreeing
    # valid witnesses remain unknown. Do not lower those thresholds.
    witnesses = []
    H = current['shape'][0]
    W = current['shape'][1]
    bands = [('viewport', 0, H, 0, W)]
    for hand, staff in current['staves'].items():
        bands.append((hand, max(0, math.floor(staff.lines[0]-1.5*staff.gap)),
                      min(H, math.ceil(staff.bottom+2*staff.gap)), 0, W))
    # A real, already source-bound contour can witness movement even when
    # stationary foreign ink or antialiased stems spoil a whole-image match.
    # These patch bounds came from the PNG scan, never renderer geometry.
    for obj in source_objects[:4]:
        x0, y0, x1, y1 = obj['bbox']
        bands.append((f"source-track-{obj['track']}", max(0, y0-2), min(H, y1+2),
                      max(0, x0-128), min(W, x1+128)))
    for label, top, bottom, left, right in bands:
        for level in (1, 0):
            try:
                shift, evidence = _translation(previous['layers'][level][top:bottom, left:right],
                    current['layers'][level][top:bottom, left:right],
                    min(s.gap for s in current['staves'].values()))
                witnesses.append((shift, evidence, level, label, top, bottom, left, right))
            except ValueError:
                pass
    # A stationary invented object can spoil whole-image correlation. Require
    # agreement from distinct photographed bands rather than lowering Dice.
    groups = [([w for w in witnesses if abs(w[0]-center[0]) <= 3]) for center in witnesses]
    ranks = [(len({w[3] for w in group}), group) for group in groups]
    if not ranks:
        raise ValueError('No mutually consistent unique photographic translation')
    rank = max(r for r, _ in ranks)
    winners = [group for r, group in ranks if r == rank]
    if max(g[0][0] for g in winners)-min(g[0][0] for g in winners) > 3:
        raise ValueError('No mutually consistent unique photographic translation')
    shift, evidence, level, label, top, bottom, left, right = winners[0][0]
    evidence['contrast_layer'] = level
    evidence['photo_band'] = label
    evidence['agreeing_bands'] = sorted({w[3] for w in winners[0]})
    # Measure the surviving phase range rather than turning high correlation
    # into an unsupported exact-position assertion.
    a = previous['layers'][level][top:bottom, left:right]
    b = current['layers'][level][top:bottom, left:right]
    scores = []
    left, right = round(a.shape[1]*.2), round(a.shape[1]*.96)
    for dx in range(shift-4, shift+5):
        lo, hi = max(left, left-dx), min(right, right-dx)
        aa, bb = a[:, lo:hi], b[:, lo+dx:hi+dx]
        score = 2*np.count_nonzero(aa & bb)/max(1, int(aa.sum()+bb.sum()))
        scores.append((score, dx))
    best = max(v for v, _ in scores)
    feasible = [dx for v, dx in scores if v >= best-.03]
    error = max(abs(dx-shift) for dx in feasible)+.5
    if error > MAX_POSITION_ERROR or shift > error:
        raise ValueError('Photo translation has excessive phase uncertainty or reverses')
    if abs(shift)+2*error > 2*STRIPE_HALF_WIDTH-6:
        raise ValueError('Photographed stripe travel leaves an uncovered interval')
    evidence.update(position_error=error, rho_bounds=[max(0., (-shift-error)/dt),
                                                    (-shift+error)/dt])
    return shift, evidence


def _areas(photo, previous, shift, whole):
    H, W = photo['shape']
    if whole or previous is None or shift is None:
        return [[0, 0, W, H]]
    x = round(photo['camera'] if photo['camera'] is not None else W*.42)
    areas = [[max(0, x-STRIPE_HALF_WIDTH), 0, min(W, x+STRIPE_HALF_WIDTH), H]]
    old = _shifted(previous['layers'][0], shift)
    # One-pixel registration tolerance selects expensive SEARCH regions only.
    # It never authorizes pixels or removes residual ink from the result.
    near = old.copy()
    for dy, dx in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        near |= np.roll(old, (dy, dx), axis=(0, 1))
    now = photo['layers'][0]
    prior = previous['layers'][0]
    back = _shifted(now, -shift)
    back_near = back.copy()
    for dy, dx in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        back_near |= np.roll(back, (dy, dx), axis=(0, 1))
    # Unchanged fixed ink was already searched in the opening endcap.
    # Include removals too: erasing a solid object can reveal a NEW family
    # without adding any pale pixel. Neither test is an ownership mask.
    novel = (now & ~near & ~prior) | (prior & ~now & ~back_near)
    # Full-height strips avoid missing a flag/stem whose new ink is only at
    # one endpoint; the padding is not an ownership mask.
    for left in range(0, W, 128):
        if novel[:, left:left+128].any():
            areas.append([max(0, left-100), 0, min(W, left+228), H])
    merged = []
    for a in sorted(areas):
        if merged and a[0] <= merged[-1][2]:
            merged[-1][2] = max(a[2], merged[-1][2])
        else:
            merged.append(a)
    return merged


def _bind(written, events, photo, objects, owners, errors):
    """Attach source identities only to fresh photographed onset contours."""
    camera = photo['camera']
    if camera is None:
        errors.extend(e['source']['id'] for e in events)
        return
    notes = [e for e in events if e['kind'] == 'note' and e['visible']]
    # Existing strict joint registration uses the public fixed playhead.
    # Reindex to the actual PNG playhead (integer pixels, no resampling).
    dx = round(photo['shape'][1]*.42-camera)
    heads, failures = {}, {}
    for level in (1, 0):
        pixels = _shifted(photo['layers'][level], dx)
        matched, failed = _register(pixels, photo['staves'], written, notes, _feature_glyphs(),
            occlusion_columns=tuple(int(c+dx) for c in photo['occlusion_columns']))
        for sid, head in matched.items():
            heads.setdefault(sid, head)
        failures.update(failed)
    failures = {sid: reason for sid, reason in failures.items() if sid not in heads}
    errors.extend(failures)
    for event in events:
        if not event['visible']:
            continue
        sid = event['source']['id']
        if event['kind'] == 'note':
            if sid not in heads:
                continue
            head = heads[sid]
            target_x, target_y = head['x']-dx, head['y']
            candidates = [o for o in objects if o['family'] == 'head'
                and abs((o['bbox'][0]+o['bbox'][2])/2-target_x) <= 3
                and abs(o['bbox'][1]-(_feature_glyphs()[o['name']]['bounds'][1]*o['gap']/250)-target_y) <= 3]
        else:
            candidates = [o for o in objects if o['family'] == 'rest'
                and abs((o['bbox'][0]+o['bbox'][2])/2-camera) <= 4
                and o['name'] == 'rest_'+str(event['note_type'])]
            if event['note_type'] in ('whole', 'half'):
                def orientation(obj):
                    x0, y0, x1, y1 = obj['bbox']
                    ys, xs = np.nonzero(photo['layers'][0][y0:y1, x0:x1])
                    if not len(xs):
                        return None
                    box = [x0+int(xs.min()), y0+int(ys.min()),
                           x0+int(xs.max())+1, y0+int(ys.max())+1]
                    return _rectangular_rest_orientation(box, photo['staves'][event['staff']])['observed_rest']
                candidates = [o for o in objects if o['family'] == 'rest'
                    and o['name'] in ('rest_whole', 'rest_half')
                    and abs((o['bbox'][0]+o['bbox'][2])/2-camera) <= 4
                    and orientation(o) == event['note_type']]
            rail = photo['staves'][event['staff']]
            candidates = [o for o in candidates if rail.lines[0]-4*rail.gap <=
                          (o['bbox'][1]+o['bbox'][3])/2 <= rail.bottom+4*rail.gap]
        if len(candidates) != 1:
            errors.append(sid)
            continue
        track = candidates[0]['track']
        if track in owners and owners[track] != sid:
            owners[track] = None
            errors.append(sid)
        else:
            owners[track] = sid


def _anchor_tree(anchors):
    """Small spatial index of scalar source anchors; no pixel cache."""
    if not anchors:
        return None
    anchors = sorted(anchors, key=lambda a: a['bbox'][0]-a['travel'])
    middle = len(anchors)//2
    return (min(a['bbox'][0]-a['travel'] for a in anchors),
            max(a['bbox'][0]-a['travel'] for a in anchors),
            min(a['error'] for a in anchors), max(a['error'] for a in anchors),
            anchors[middle], _anchor_tree(anchors[:middle]), _anchor_tree(anchors[middle+1:]))


def _possible_owner(tree, world_x, error):
    pending, visits = [tree], 0
    while pending:
        node = pending.pop()
        if node is None:
            continue
        visits += 1
        if visits > 256:
            return True  # Bounded computation cannot justify an extra.
        low, high, first_error, last_error, anchor, left, right = node
        radius = max(abs(error-first_error), abs(error-last_error))+3
        if not low-radius <= world_x <= high+radius:
            continue
        if abs(world_x-(anchor['bbox'][0]-anchor['travel'])) <= abs(error-anchor['error'])+3:
            return True
        pending.extend((left, right))
    return False


def _playhead_occludes_candidate(photo, obj):
    """A foreground candidate crossed by colored ink cannot be excluded.

    Only actual photographed overlap counts. An extra glyph elsewhere is
    still subject to the strict source-exclusion and contour checks.
    """
    left, top, right, bottom = obj['bbox']
    return bool(photo['occlusion'][top:bottom, left:right].any())


def _isolated_rectangle(photo, obj):
    """A ledger/head/stem intersection is not an independently seen rest."""
    x0, y0, x1, y1 = obj['bbox']
    template = _template(obj['name'], obj['gap'])
    layer = photo['layers'][0]
    yy, xx = np.nonzero(template & layer[y0:y1, x0:x1])
    support = frozenset(((yy+y0)*layer.shape[1]+xx+x0).tolist())
    component = _closed_component(layer, dict(bbox=obj['bbox'], support=support))
    if not component:
        return False
    ys, xs = np.divmod(np.array(tuple(component)), layer.shape[1])
    box = [int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1]
    for staff in photo['staves'].values():
        center = (staff.lines[0]+staff.bottom)/2
        if abs((box[1]+box[3])/2-center) <= 4*staff.gap:
            if _rectangular_rest_orientation(box, staff)['observed_rest'] in ('whole', 'half'):
                return True
    return False


def verify_extra_symbol_pixels(xml, folder, *, hand='both'):
    """Return ordinary frame/region observations and honest absence coverage.

    ``hand`` validates the request; ALL written hands are inventoried because
    inactive ink remains physically visible. Read only actual native-*.png
    and independent source XML/font resources. Supplied native reports are
    neither necessary nor sufficient. At most two decoded frames are live.

    This first bounded implementation proves source head/rest track ownership
    and detects unrequired detached dot/flag families. General adornment and
    connector pixel ownership is explicitly unresolved, so residual ink blocks
    full-scope certification even when every expected source symbol passes.
    """
    if hand not in ('both', 'right', 'left'):
        raise ValueError('Unknown hand')
    written = read_written_score(xml)
    controls = {'clef_'+sign.lower() for _, _, sign, _, _ in written.clefs if sign in ('G', 'F', 'C')}
    controls.update('time_'+digit for _, meter in written.meter for value in meter
                    for digit in str(value) if digit.isdigit())
    folder = Path(folder)
    paths = {}
    for path in folder.glob('native-*.png'):
        try:
            clock = float(path.stem.removeprefix('native-'))
        except ValueError:
            continue
        if math.isfinite(clock):
            paths[clock] = path
    clocks = sorted(paths)
    events = defaultdict(list)
    for event in written.symbols:
        events[float(f"{float(event['beat']):.5f}")].append(event)
    ending = float(written.bars[-1]) if written.bars else 0.
    gaps = [[a, b] for a, b in zip(clocks, clocks[1:]) if b-a > MAX_CLOCK_STEP+.000011]
    missing = [clock for clock in events if clock not in paths]
    owners, binding_errors, tracks, snapshots, motions = {}, [], 0, [], []
    source_anchors = {}
    travel, travel_error = 0, 0.
    previous, previous_objects, previous_clock = None, [], None
    motion_errors = []
    for index, clock in enumerate(clocks):
        try:
            photo = _photo(paths[clock])
            shift, motion = None, None
            if previous is not None:
                try:
                    source_objects = [o for o in previous_objects if owners.get(o['track']) is not None]
                    shift, motion = _motion(previous, photo, clock-previous_clock, source_objects)
                except (ValueError, AssertionError, KeyError) as exc:
                    motion_errors.append(dict(clock=clock, reason=str(exc)))
            areas = _areas(photo, previous, shift, index in (0, len(clocks)-1))
            objects = _scan(photo, areas, controls=controls)
            # Recheck carried contours at their measured position. A track
            # never authorizes a vanished or changed glyph in a later PNG.
            if shift is not None:
                for old in previous_objects:
                    box = old['bbox']
                    template = _template(old['name'], old['gap'])
                    h, w = template.shape
                    for offset in {shift, 0}:
                        x, y = box[0]+offset, box[1]
                        if not (0 <= x < photo['shape'][1]-w and 0 <= y < photo['shape'][0]-h):
                            continue
                        if any(o['family'] == old['family'] and _overlap(o['bbox'], [x, y, x+w, y+h]) > .65*w*h for o in objects):
                            continue
                        score = max(2*np.count_nonzero(layer[y:y+h, x:x+w] & template)/
                                    max(1, int(template.sum()+layer[y:y+h, x:x+w].sum()))
                                    for layer in photo['layers'])
                        if score >= (.90 if old['family'] == 'dot' else .79):
                            objects.append(dict(name=old['name'], family=old['family'],
                                bbox=[x, y, x+w, y+h], gap=old['gap'], score=round(score, 5)))
            used = set()
            for obj in objects:
                candidates = [] if shift is None else [o for o in previous_objects
                    if o['family'] == obj['family'] and o['track'] not in used
                    and (abs(o['bbox'][0]+shift-obj['bbox'][0]) <= 3 or
                         (owners.get(o['track']) is None and abs(o['bbox'][0]-obj['bbox'][0]) <= 3))
                    and abs(o['bbox'][1]-obj['bbox'][1]) <= 3]
                if len(candidates) == 1:
                    obj['track'] = candidates[0]['track']
                    used.add(obj['track'])
                else:
                    obj['track'] = tracks
                    tracks += 1
            _bind(written, events.get(clock, []), photo, objects, owners, binding_errors)
            if motion:
                travel += shift
                travel_error += motion['position_error']
            current_ids = {e['source']['id'] for e in events.get(clock, [])}
            for obj in objects:
                sid = owners.get(obj['track'])
                if sid in current_ids:
                    source_anchors[sid] = dict(bbox=obj['bbox'], travel=travel,
                                              error=travel_error, gap=obj['gap'])
            snapshots.append(dict(clock=clock, frame=paths[clock].name, objects=objects,
                                  areas=areas, motion=motion, shape=photo['shape'],
                                  travel=travel, travel_error=travel_error))
            if motion:
                motions.append(motion)
            previous, previous_objects, previous_clock = photo, objects, clock
        except (ValueError, AssertionError, KeyError, OSError) as exc:
            snapshots.append(dict(clock=clock, frame=paths[clock].name, error=str(exc), objects=[]))
            motion_errors.append(dict(clock=clock, reason=str(exc)))
            previous, previous_objects, previous_clock = None, [], clock
    del previous
    source_by_id = {e['source']['id']: e for e in written.symbols if e['visible']}
    bound = {sid for sid in owners.values() if sid is not None}
    source_counts = Counter(e['kind'] for e in source_by_id.values())
    bound_counts = Counter(source_by_id[sid]['kind'] for sid in bound)
    source_supported = not written.uncovered and not written.issues
    all_heads = bound_counts['note'] == source_counts['note'] and not missing and not gaps and not motion_errors and source_supported
    all_rests = bound_counts['rest'] == source_counts['rest'] and not missing and not gaps and not motion_errors and source_supported
    anchor_lanes = defaultdict(list)
    for sid, anchor in source_anchors.items():
        anchor_lanes[source_by_id[sid]['kind'], anchor['bbox'][1]].append(anchor)
    anchor_trees = {key: _anchor_tree(values) for key, values in anchor_lanes.items()}
    expected_dots = sum(e['dots'] for e in source_by_id.values())
    expected_flags = any(e['note_type'] in ('eighth', '16th', '32nd', '64th', '128th')
                         and not e['beams'] for e in source_by_id.values() if e['kind'] == 'note')
    measured, unowned_total, certified = [], 0, 0
    for snapshot in snapshots:
        if 'error' in snapshot:
            measured.append(dict(frame=snapshot['frame'], clock=snapshot['clock'], region='viewport',
                                 status='unverified', reason=snapshot['error'], evidence={}))
            continue
        photo = _photo(folder/snapshot['frame'])
        claimed = np.zeros(photo['shape'], dtype=bool)
        unexpected, unresolved = [], []
        for obj in snapshot['objects']:
            x0, y0, x1, y1 = obj['bbox']
            owner = owners.get(obj['track'])
            if owner is not None:
                # Tight original reference support, never its whole box or
                # the whole actual connected component (which can hide extras).
                claimed[y0:y1, x0:x1] |= _template(obj['name'], obj['gap']) & photo['ink'][y0:y1, x0:x1]
                continue
            other = [o for o in snapshot['objects'] if o is not obj and
                     _overlap(o['bbox'], obj['bbox']) > .5*(x1-x0)*(y1-y0)]
            definitive = ((obj['family'] == 'head' and all_heads)
                          or (obj['family'] == 'rest' and all_rests)
                          or (obj['family'] == 'dot' and not expected_dots and source_supported)
                          or (obj['family'] == 'flag' and not expected_flags and source_supported))
            # An actual chord head in Ala beat 0.90000 is crossed by the
            # turquoise playhead; incomplete ink cannot prove an extra note.
            if _playhead_occludes_candidate(photo, obj):
                definitive = False
            if obj['name'] in ('rest_whole', 'rest_half') and not _isolated_rectangle(photo, obj):
                definitive = False
            if definitive and not other and obj['family'] in ('head', 'rest'):
                # A lost contour track is not evidence of an invented note.
                # Conservative accumulated photo-error intervals can EXCLUDE
                # an owner, but never authorize a source pixel mask. Ownership
                # above still needs actual local <=3px contour registration.
                kind = 'note' if obj['family'] == 'head' else 'rest'
                for y in range(y0-3, y0+4):
                    if _possible_owner(anchor_trees.get((kind, y)),
                                       x0-snapshot['travel'], snapshot['travel_error']):
                        definitive = False
                        break
            record = dict(family=obj['family'], glyph=obj['name'], bbox=obj['bbox'],
                          score=obj['score'], track=obj['track'])
            # Competing larger authentic glyphs (e.g. a clef bowl) make a
            # small internal family candidate ambiguous, not an invented note.
            (unexpected if definitive and not other else unresolved).append(record)
        residual = photo['ink'] & ~claimed
        count = int(residual.sum())
        unowned_total += count
        incomplete = bool(count or unresolved or photo['occluded'])
        status = 'mismatch' if unexpected else 'unverified' if incomplete else 'verified'
        measured.append(dict(frame=snapshot['frame'], clock=snapshot['clock'], region='viewport',
            status=status, reason=('Unowned authentic timed-symbol contour' if unexpected else
            'Unowned ink or an opaque colored intersection prevents an absence claim' if incomplete else
            'Every observed foreground pixel has measured source ownership'),
            evidence=dict(unexpected=unexpected, unresolved=unresolved, unowned_pixels=count,
                          occluded_pixels=photo['occluded'],
                          scanned_areas=snapshot['areas'], motion=snapshot['motion'],
                          owned_objects=sum(owners.get(o['track']) is not None for o in snapshot['objects']))))
        # Independently empty viewport tiles are useful positive bounded
        # observations even while other regions remain unsupported.
        H, W = photo['shape']
        clear_tiles = []
        for left in range(0, W, 128):
            for top in range(0, H, 128):
                right, bottom = min(W, left+128), min(H, top+128)
                blocked = any(_overlap([left, top, right, bottom], o['bbox'])
                              for o in unresolved+unexpected)
                if (not blocked and not residual[top:bottom, left:right].any()
                        and not photo['occlusion'][top:bottom, left:right].any()):
                    certified += 1
                    clear_tiles.append([left, top, right, bottom])
        measured[-1]['evidence']['clear_or_owned_tiles'] = len(clear_tiles)
        if clear_tiles:
            measured.append(dict(frame=snapshot['frame'], clock=snapshot['clock'],
                region='clear_or_owned_tiles', status='verified',
                reason='Measured tiles contain no unexplained contrasting ink or colored occluder',
                evidence=dict(bboxes=clear_tiles, contrast_floor=4)))
    def endcap(snapshot):
        if 'error' in snapshot:
            return False
        H, W = snapshot['shape']
        return snapshot['areas'] == [[0, 0, W, H]]
    initial = bool(clocks and abs(clocks[0]) < .000011 and endcap(snapshots[0]))
    terminal = bool(clocks and abs(clocks[-1]-ending) < .000011 and endcap(snapshots[-1]))
    motion_ok = initial and terminal and not gaps and not motion_errors and len(motions) == max(0, len(clocks)-1)
    coverage = dict(frames=len(clocks), expected_heads=source_counts['note'], expected_rests=source_counts['rest'],
        measured_frames=sum('error' not in snapshot for snapshot in snapshots),
        bound_heads=bound_counts['note'], bound_rests=bound_counts['rest'],
        initial_viewport=initial, terminal_viewport=terminal,
        motion_status='verified' if motion_ok else 'unverified', clock_gaps=gaps,
        motion_errors=motion_errors, missing_source_clocks=missing,
        binding_errors=sorted(set(binding_errors)), unowned_pixels=unowned_total,
        source_supported=source_supported,
        certified_tiles=certified, decoded_frame_cache_limit=2,
        full_absence_status='unverified')
    return dict(measured=measured, coverage=coverage, complete=False,
        scope='bounded sampled regions', limits=[
            'Finite snapshots cannot exclude transients between capture clocks.',
            'Raster-identical overprinting and ink identical to an occluding rail cannot be distinguished.',
            'Unowned adornments, headers, connectors, clipping and opaque intersections remain unverified.',
            'Dot/flag ownership with nonzero source obligations is not yet established by this checker.'])

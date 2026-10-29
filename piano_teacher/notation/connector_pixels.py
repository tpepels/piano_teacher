"""Source-bound beam/tuplet witnesses, independent of native fragment assets.

Expectations come from MusicXML and original Verovio SVG graphics. Staffs,
heads, stems and horizontal registration come only from actual PNGs. Results
describe bounded construct coverage, not a whole-score pass.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
from io import BytesIO
import math
from pathlib import Path
import re
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

from ..source_svg import isolate
from ..source_svg import parse_svg_geometry
from .proof import read_written_score
from .raster_matching import match_glyph
from .captured_frames import CapturedFrames

STATUSES = ('verified', 'unverified', 'ambiguous', 'unsupported', 'mismatch')
TYPES = {'eighth': 1, '16th': 2, '32nd': 3, '64th': 4, '128th': 5}


def _classes(node):
    return set(node.get('class', '').split())


def _real(node):
    return not _classes(node) & {'bounding-box', 'content-bounding-box'}


def _art(group, kind):
    """Only graphics owned by this group, excluding nested source events."""
    for child in group:
        if not _real(child) or _classes(child) & {'note', 'chord', 'rest', 'mRest', 'tuplet', 'beam'}:
            continue
        if kind == 'beam' and child.tag.rsplit('}', 1)[-1] in {'polygon', 'path'}:
            yield child
        elif kind != 'beam' and kind in _classes(child):
            yield child
        else:
            yield from _art(child, kind)


def _semantic_groups(written, kind):
    lanes = defaultdict(list)
    for event in written.symbols:
        if not event['chord']:
            lanes[event['part_index'], event['index'], event['staff'], event['voice']].append(event)
    groups = []
    for events in lanes.values():
        opened = {}
        for event in sorted(events, key=lambda e: e['beat']):
            marks = event['tuplet_marks'] if kind == 'tuplet' else [
                (value, level, '', '') for level, value, _ in event['beams'] if level == '1']
            for mark in marks:
                if mark[0] in {'start', 'begin'}:
                    if mark[1] in opened:
                        groups.append((opened.pop(mark[1])[0], None))
                    opened[mark[1]] = ([], mark)
            for members, _mark in opened.values():
                members.append(event)
            for mark in marks:
                if mark[0] in {'stop', 'end'}:
                    members, start = opened.pop(mark[1], ([], None))
                    groups.append((members or [event], start))
        groups.extend((members, None) for members, _ in opened.values())
    return groups


def _staff_bindings(staff, events, geom, explicit):
    """Pair complete visible voices with uniquely identified printed layers.

    Hidden cursor padding has no graphical identity. In a polyphonic staff,
    preserved source IDs must identify each layer; neither its position nor
    an anonymous rest's appearance can choose between source voices.
    """
    lanes = defaultdict(list)
    for event in events:
        if event['visible']:
            lanes[event['voice']].append(event)
    layers = [n for n in staff if 'layer' in _classes(n) and _real(n)] or [staff]
    sequences = [[n for n in layer.iter() if _real(n)
                  and _classes(n) & {'note', 'rest', 'mRest', 'multiRest'}
                  and n.get('id') in geom.elements] for layer in layers]
    sequences = [nodes for nodes in sequences if nodes]
    identifiers = [n.get('id') for nodes in sequences for n in nodes]
    if len(sequences) != len(lanes) or len(identifiers) != len(set(identifiers)):
        return []
    bindings, used = [], set()
    for nodes in sequences:
        candidates = []
        for voice, required in lanes.items():
            if len(nodes) != len(required):
                continue
            if not all((('note' in _classes(node)) == (event['kind'] == 'note'))
                       and (event['id'] == node.get('id') and len(explicit[event['id']]) == 1
                            if event['id'] else not explicit[node.get('id')])
                       for node, event in zip(nodes, required)):
                continue
            if len(lanes) > 1 and not any(event['id'] for event in required):
                continue
            candidates.append((voice, required))
        if len(candidates) != 1 or candidates[0][0] in used:
            return []
        voice, required = candidates[0]
        used.add(voice)
        bindings.extend(zip(nodes, required))
    return bindings if used == set(lanes) else []


def _pages(written, strings):
    """Complete structural binding; never nearest-rest or native-model aliases.

    Every visible source voice's event order/count/kind and preserved XML ID
    must agree with one complete SVG layer. Unanchored polyphony stays unknown.
    """
    pages = [(ET.fromstring(svg), parse_svg_geometry(svg)) for svg in strings]
    measures = [(p, node) for p, (root, _) in enumerate(pages)
                for node in root.iter() if 'measure' in _classes(node) and _real(node)]
    indices = sorted({e['index'] for e in written.symbols})
    aliases = {}
    # XML IDs are independent of Verovio's pagination/measure count.
    # Never discard them when a printed system splits or repeats a measure.
    explicit = defaultdict(list)
    for event in written.symbols:
        if event['id']:
            explicit[event['id']].append(event)
    for page, (_root, geom) in enumerate(pages):
        for identifier in geom.elements:
            if len(explicit[identifier]) == 1:
                aliases[page, identifier] = explicit[identifier][0]
    if len(measures) == len(indices):
        matched_measures = list(zip(indices, measures))
    else:
        # A reference print can insert/split measure containers without
        # changing the source XML event identities. Anchor a measure through
        # unique preserved note/rest IDs instead of abandoning *all*
        # anonymous-rest binding on the page. Do not guess an unanchored
        # measure by position or by its musical content.
        matched_measures = []
        for page, measure in measures:
            anchored_indices = {
                explicit[node.get('id')][0]['index']
                for node in measure.iter()
                if _classes(node) & {'note', 'rest', 'mRest', 'multiRest'}
                and len(explicit[node.get('id')]) == 1
            }
            if len(anchored_indices) == 1:
                matched_measures.append((next(iter(anchored_indices)), (page, measure)))
    match_counts = Counter(index for index, _ in matched_measures)
    for index, (page, measure) in matched_measures:
        if match_counts[index] != 1:
            # Multiple reference measure containers may contain pieces of
            # one source measure. Their anonymous event order is not unique.
            continue
        expected = defaultdict(list)
        for event in written.symbols:
            if event['index'] == index:
                expected[event['part_index'], event['raw_staff']].append(event)
        staves = [n for n in measure if 'staff' in _classes(n) and _real(n)]
        if len(staves) != len(expected):
            continue
        for staff, (_lane, events) in zip(staves, sorted(expected.items())):
            for node, event in _staff_bindings(staff, events, pages[page][1], explicit):
                if event['id'] or event['kind'] != 'rest':
                    continue
                identifier = node.get('id')
                if (page, identifier) not in aliases:
                    aliases[page, identifier] = event
    return pages, aliases


@lru_cache(maxsize=8)
def _raster(svg, space):
    """Rasterize original graphics at a fixed reference staff scale."""
    import cairosvg
    geom = parse_svg_geometry(svg)
    width = max(1, round(geom.width * 24 / (space * geom.height)))
    if width > 18000:
        raise ValueError('Reference raster exceeds bounded width')
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=width)
    with Image.open(BytesIO(png)) as picture:
        mask = np.asarray(picture.convert('RGBA'))[:, :, 3] > 96
    return mask


def _reference_art(root, nodes, geom, events, identifiers):
    anchors = [geom.elements[i] for i in identifiers]
    system = anchors[0][2]
    if any(a[2] != system for a in anchors):
        raise ValueError('Connector spans reference systems')
    rails = geom.staff_systems[system]['staff_lines']
    space = rails[1] - rails[0]
    # Preserve complete original ancestry/defs for each owned graphic.
    masks = [_raster(isolate(root, node), space) for node in nodes]
    if not masks:
        return None
    mask = np.logical_or.reduce(masks)
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    scale = 24 / (space * geom.height)
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)]
    return dict(mask=mask[bbox[1]:bbox[3], bbox[0]:bbox[2]].copy(), gap=24.,
                anchors=[(x*geom.width*scale, y*geom.height*scale) for x, y, _ in anchors],
                stem_xs=[geom.stem_x.get(i, float('nan'))*geom.width*scale for i in identifiers],
                bbox=bbox)


def _inventory(written, strings, kind, hand):
    pages, aliases = _pages(written, strings)
    semantic = _semantic_groups(written, kind)
    expected = []
    used = set()
    for page, (root, geom) in enumerate(pages):
        for group in root.iter():
            if kind not in _classes(group) or not _real(group):
                continue
            ids = [n.get('id') for n in group.iter() if _real(n)
                   and _classes(n) & {'note', 'rest', 'mRest', 'multiRest'}]
            members = [aliases.get((page, i)) for i in ids]
            if not ids:
                # Verovio emits class=tuplet around invisible class=space
                # placeholders. No glyph and no source members means this
                # wrapper is not a graphical obligation. Explicit semantic
                # tuplet obligations are still checked below.
                if kind == 'tuplet' and not (list(_art(group, 'tupletNum'))
                                              or list(_art(group, 'tupletBracket'))):
                    continue
                expected.append(dict(events=[], ids=ids, group=group.get('id'),
                                     error='Graphical connector has no bound source events'))
                continue
            if any(e is None for e in members):
                expected.append(dict(events=[], ids=ids, group=group.get('id'),
                                     error='Reference source event IDs are absent or ambiguous'))
                continue
            if hand != 'both' and all(e['staff'] != hand for e in members):
                continue
            leaders = [e for e in members if not e['chord']]
            key = tuple(e['source']['id'] for e in leaders)
            if key in used:
                expected.append(dict(events=members, ids=ids, error='Duplicate reference group binding'))
                continue
            used.add(key)
            row = dict(events=members, ids=ids, leaders=leaders, page=page,
                       group=group.get('id'), error=None)
            if (len({(e['part_index'], e['index'], e['staff'], e['voice']) for e in members}) != 1
                    or any(a['beat'] >= b['beat'] for a, b in zip(leaders, leaders[1:]))):
                row['error'] = 'Cross-staff/voice or non-monotone connector requires disambiguation'
            try:
                if kind == 'beam':
                    row['art'] = _reference_art(root, list(_art(group, 'beam')), geom, members, ids)
                else:
                    row['number'] = _reference_art(root, list(_art(group, 'tupletNum')), geom, members, ids)
                    row['bracket'] = _reference_art(root, list(_art(group, 'tupletBracket')), geom, members, ids)
                    nodes = list(_art(group, 'tupletNum'))
                    row['number_parts'] = [_reference_art(root, [child], geom, members, ids)
                        for node in nodes for child in node.iter() if child.tag.rsplit('}', 1)[-1] == 'use']
                    row['numeral_codes'] = [re.search(r'#(E[0-9A-F]{3})', value).group(1)
                        for node in nodes for child in node.iter()
                        for name, value in child.attrib.items()
                        if name.rsplit('}', 1)[-1] == 'href' and re.search(r'#(E[0-9A-F]{3})', value)]
                row['geom'] = geom
            except (ValueError, KeyError, IndexError) as exc:
                row['error'] = str(exc)
            expected.append(row)
    for members, mark in semantic:
        if hand != 'both' and all(e['staff'] != hand for e in members):
            continue
        key = tuple(e['source']['id'] for e in members)
        matching = [r for r in expected if tuple(e['source']['id'] for e in r.get('leaders', [])) == key]
        if matching:
            for row in matching:
                row['mark'] = mark
                if kind == 'tuplet' and mark and mark[2:] == ('no', 'none'):
                    row.update(graphical=False, error='Hidden source marker has no pixel obligation')
        elif key not in used:
            hidden = kind == 'tuplet' and mark and mark[2:] == ('no', 'none')
            expected.append(dict(events=members, leaders=members, ids=[e['id'] for e in members],
                mark=mark, graphical=not hidden, error='Hidden source marker has no pixel obligation' if hidden
                else 'Explicit source group lacks unambiguous reference artwork'))
    if not strings and not expected:
        # Even auto-beamed short types cannot become vacuously complete.
        members = [e for e in written.symbols if e['kind'] == 'note' and e['note_type'] in TYPES
                   and (hand == 'both' or e['staff'] == hand)]
        if members:
            expected.append(dict(events=members, ids=[e['id'] for e in members],
                                 error='Original Verovio reference SVG is missing'))
    return expected


def _runs(values):
    a = np.flatnonzero(values)
    return [(int(p[0]), int(p[-1])+1) for p in np.split(a, np.flatnonzero(np.diff(a)>1)+1) if len(p)]


def _reference_column(art, x):
    column = round(x)-art['bbox'][0]
    return _runs(art['mask'][:, column]) if 0 <= column < art['mask'].shape[1] else []


def _stem(pixels, anchors, up):
    gap = anchors[0]['gap']
    outer = max(anchors, key=lambda a: a['y']) if up else min(anchors, key=lambda a: a['y'])
    high, low = min(a['y'] for a in anchors), max(a['y'] for a in anchors)
    center = outer['x']
    left, right = (center+.3*gap, center+.9*gap) if up else (center-.9*gap, center-.3*gap)
    candidates = []
    for x in range(math.floor(left), math.ceil(right)+1):
        if not 0 <= x < pixels.shape[1]:
            continue
        for top, bottom in _runs(pixels[:, x]):
            if up:
                valid = top <= high-1.25*gap and bottom >= low-.3*gap and bottom <= low+.5*gap
            else:
                valid = bottom >= low+1.25*gap and top <= high+.3*gap and top >= high-.5*gap
            if valid and bottom-top <= 12*gap:
                candidates.append((bottom-top, x, top, bottom))
    if not candidates:
        raise ValueError('Actual head-to-beam stem attachment is absent or interrupted')
    # A broad connected object cannot stand in for a thin stem.
    columns = sorted({c[1] for c in candidates})
    if columns[-1]-columns[0] > .24*gap:
        raise ValueError('Stem attachment is ambiguous or too broad')
    _length, _x, top, bottom = max(candidates)
    return dict(x=float(np.mean(columns)), top=top, bottom=bottom,
                bbox=[min(columns), top, max(columns)+1, bottom])


def _beam(row, frames, target):
    events, art = row['events'], row.get('art')
    if art is None:
        raise ValueError('Reference beam has no isolated polygon ink')
    anchors = frames.anchors(events, target)
    frame = frames.frame(target)
    gap = anchors[0]['gap']
    up = (art['bbox'][1]+art['bbox'][3])/2 < art['anchors'][0][1]
    chords = []
    for event, anchor in zip(events, anchors):
        if not event['chord']:
            chords.append([])
        chords[-1].append(anchor)
    for chord in chords:
        center = (max(chord, key=lambda a: a['y']) if up else min(chord, key=lambda a: a['y']))['x']
        lo, hi = (center+.3*gap, center+.9*gap) if up else (center-.9*gap, center-.3*gap)
        if any(lo <= x <= hi for x in frame['occluded_columns']):
            raise ValueError('Measured coloured playhead occludes an actual stem attachment')
    try:
        stems = [_stem(frame['pixels'], chord, up) for chord in chords]
    except ValueError as exc:
        return 'mismatch', str(exc), dict(anchors=anchors)
    if any(stems[0]['x'] <= x <= stems[-1]['x'] for x in frame['occluded_columns']):
        raise ValueError('Measured coloured playhead occludes an interior beam column')
    leaders = row['leaders']
    primary_marks = [[value for level, value, _ in e['beams'] if level == '1'] for e in leaders]
    if any(primary_marks):
        expected_marks = [['begin'], *[['continue'] for _ in leaders[1:-1]], ['end']]
        if primary_marks != expected_marks:
            raise ValueError('Source beam begin/continue/end boundaries disagree with reference group')
    ref_indices = [i for i, e in enumerate(events) if not e['chord']]
    ref_xs = [art['stem_xs'][i] for i in ref_indices]
    if not all(math.isfinite(x) for x in ref_xs):
        raise ValueError('Original reference stem anchors are missing')
    for event, x in zip(leaders, ref_xs):
        level = max((len(_reference_column(art, x+offset)) for offset in (-8, -5, 5, 8)), default=0)
        if level != TYPES.get(event['note_type']):
            raise ValueError('Written beam level does not agree with reference identity')
    for index, event in enumerate(leaders):
        for number, value, _attrs in event['beams']:
            level = int(number)
            left = index > 0 and len(_reference_column(art, (ref_xs[index-1]+ref_xs[index])/2)) >= level
            right = index+1 < len(ref_xs) and len(_reference_column(art, (ref_xs[index]+ref_xs[index+1])/2)) >= level
            if value not in {'begin', 'continue', 'end', 'forward hook', 'backward hook'}:
                raise ValueError('Source beam mark is unsupported')
            wanted = (value in {'continue', 'end'}, value in {'begin', 'continue'})
            if (left, right) != wanted:
                raise ValueError('Source beam connectivity disagrees with original reference graphic')
    # Source SVG glyph origins are not presumed to be PNG head centres.
    # Compare every interior column, preserving original partial hooks.
    samples = []
    beam_box = [stems[0]['x'], frame['pixels'].shape[0], stems[-1]['x']+1, 0]
    for i in range(len(stems)-1):
        if stems[i+1]['x']-stems[i]['x'] < 1.3*gap:
            raise ValueError('Beam endpoints are not optically separable')
        start, end = math.ceil(stems[i]['x']+.15*gap), math.floor(stems[i+1]['x']-.15*gap)
        for x in range(start, end+1):
            fraction = (x-stems[i]['x'])/(stems[i+1]['x']-stems[i]['x'])
            sx = round(ref_xs[i]+(ref_xs[i+1]-ref_xs[i])*fraction)
            runs = _reference_column(art, sx)
            if not runs:
                raise ValueError('Reference beam interval has no primary contour')
            tip_a = stems[i]['top'] if up else stems[i]['bottom']-1
            tip_b = stems[i+1]['top'] if up else stems[i+1]['bottom']-1
            tip = tip_a+(tip_b-tip_a)*fraction
            lo, hi = max(0, round(tip-1.5*gap)), min(frame['pixels'].shape[0], round(tip+1.5*gap))
            observed = [(a+lo, b+lo) for a, b in _runs(frame['pixels'][lo:hi, x])]
            expected_thickness = [(b-a)*gap/24 for a, b in runs]
            expected_separation = [(a-runs[0][0])*gap/24 for a, _ in runs]
            fit = len(observed) == len(runs)
            if fit:
                fit = all(abs((b-a)-thickness) <= max(1.5, .10*gap)
                          for (a, b), thickness in zip(observed, expected_thickness))
                fit &= all(abs((a-observed[0][0])-separation) <= max(1.5, .10*gap)
                           for (a, _), separation in zip(observed, expected_separation))
            if not fit:
                return 'mismatch', 'Actual beam level/thickness/spacing differs from original source graphic', dict(
                    samples=samples, failed_sample=dict(x=x, expected_levels=len(runs), observed=observed))
            beam_box[1] = min(beam_box[1], observed[0][0])
            beam_box[3] = max(beam_box[3], observed[-1][1])
            samples.append(dict(x=x, levels=len(runs), thickness_spaces=[round((b-a)/gap, 3) for a, b in observed]))
    # Every column must carry the primary beam; three probes alone could
    # miss an erasure between them. Restrict to the independently found tips.
    continuity = []
    for a, b in zip(stems, stems[1:]):
        for x in range(math.ceil(a['x']), math.floor(b['x'])+1):
            f = (x-a['x'])/(b['x']-a['x'])
            tip = (a['top'] if up else a['bottom']-1)*(1-f)+(b['top'] if up else b['bottom']-1)*f
            y0, y1 = max(0, round(tip-.25*gap)), min(frame['pixels'].shape[0], round(tip+.25*gap)+1)
            continuity.append(bool(frame['pixels'][y0:y1, x].any()))
    if not continuity or not all(continuity):
        return 'mismatch', 'Primary beam is interrupted between actual stem endpoints', dict(samples=samples)
    return 'verified', 'Source beam profiles and continuous attachment to every actual chord stem agree', dict(
        bbox=[math.floor(beam_box[0]), beam_box[1], math.ceil(beam_box[2]), beam_box[3]],
        anchors=anchors, stems=stems, stem_up=up, samples=samples,
        continuity_columns=len(continuity), staff_gap=gap,
        staff_lines=list(frame['staves'][events[0]['staff']].lines))


def _resized_art(art, gap):
    x0, y0, x1, y1 = art['bbox']
    image = Image.fromarray(art['mask'].astype('uint8')*255)
    return np.asarray(image.resize((max(1, round((x1-x0)*gap/24)),
                                    max(1, round((y1-y0)*gap/24))), Image.Resampling.BILINEAR)) > 96


def _fit_mask(pixels, mask, x, y, radius):
    """Bounded true contour fit including negative space and uniqueness."""
    h, w = mask.shape
    candidates = []
    for yy in range(round(y)-radius, round(y)+radius+1):
        if yy < 0 or yy+h > pixels.shape[0]:
            continue
        for xx in range(round(x)-radius, round(x)+radius+1):
            if xx < 0 or xx+w > pixels.shape[1]:
                continue
            block = pixels[yy:yy+h, xx:xx+w]
            denominator = int(mask.sum()+block.sum())
            score = float(2*np.count_nonzero(mask & block)/denominator) if denominator else 0.
            candidates.append((score, xx, yy))
    candidates.sort(reverse=True)
    if not candidates:
        raise ValueError('Reference glyph search is offscreen')
    best = candidates[0]
    rival = next((c for c in candidates if abs(c[1]-best[1])+abs(c[2]-best[2]) > max(3, min(w, h)*.5)), (0., 0, 0))
    return best, best[0]-rival[0]


def _map_x(values, source, actual, scale):
    values = np.asarray(values, dtype=float)
    if len(source) == 1:
        return actual[0]+(values-source[0])*scale
    mapped = np.interp(values, source, actual)
    return np.where(values < source[0], actual[0]+(values-source[0])*scale,
                    np.where(values > source[-1], actual[-1]+(values-source[-1])*scale, mapped))


def _bracket_mask(art, source, actual, scale, yoffset):
    """Warp the two genuine bracket halves; preserve staff-space Y scale."""
    x0, y0, x1, y1 = art['bbox']
    left, right = _map_x([x0, x1], source, actual, scale)
    box = [math.floor(left), math.floor(y0*scale+yoffset), math.ceil(right), math.ceil(y1*scale+yoffset)]
    xx = np.arange(box[0], box[2])+.5
    inverse = _map_x(xx, actual, source, 1/scale)
    yy = (np.arange(box[1], box[3])+.5-yoffset)/scale
    ix, iy = np.floor(inverse).astype(int)-x0, np.floor(yy).astype(int)-y0
    sx = np.clip(ix, 0, art['mask'].shape[1]-1)
    sy = np.clip(iy, 0, art['mask'].shape[0]-1)
    mask = art['mask'][np.ix_(sy, sx)].copy()
    mask[:, (ix < 0) | (ix >= art['mask'].shape[1])] = False
    mask[(iy < 0) | (iy >= art['mask'].shape[0]), :] = False
    return mask, box


def _bracket_topology(pixels, mask, x, y, number_box, gap):
    """All required hooks and columns, at one fixed raster registration."""
    h, w = mask.shape
    block = pixels[y:y+h, x:x+w]
    padded = np.pad(block, 1)
    supported = np.logical_or.reduce([padded[dy:dy+h, dx:dx+w]
                                      for dy in range(3) for dx in range(3)])
    for part in (slice(0, max(2, round(gap*.3))), slice(max(0, w-round(gap*.3)), w)):
        required = mask[:, part]
        height = int(np.count_nonzero(required.any(axis=1)))
        observed_height = int(np.count_nonzero(block[:, part].any(axis=1)))
        if required.sum() and (np.count_nonzero(required & supported[:, part])/required.sum() < .90
                               or observed_height < height-2):
            return 'Tuplet bracket endpoint hook is missing or detached'
    columns = np.arange(x, x+w)
    corridor = (columns >= number_box[0]-gap) & (columns < number_box[2]+gap)
    if np.any(mask.any(axis=0) & ~block.any(axis=0) & ~corridor):
        return 'Tuplet bracket is interrupted between actual source endpoints'
    return None


def _fit_bracket(pixels, mask, box, numeral, number_box, gap=None):
    """A separately proven numeral is not unexplained bracket background ink.

    Do not subtract actual bright pixels indiscriminately: remove only the
    independently matched numeral stencil. Overlapping required contours
    remain ambiguous because one opaque pixel cannot prove two symbols.
    """
    candidates = []
    h, w = mask.shape
    for y in range(box[1]-1, box[1]+2):
        for x in range(box[0]-1, box[0]+2):
            if min(x, y) < 0 or x+w > pixels.shape[1] or y+h > pixels.shape[0]:
                continue
            numbered = np.zeros_like(mask)
            nx, ny, nr, nb = number_box
            l, t, r, b = max(x, nx), max(y, ny), min(x+w, nr), min(y+h, nb)
            if l < r and t < b:
                numbered[t-y:b-y, l-x:r-x] = numeral[t-ny:b-ny, l-nx:r-nx]
            overlap = int(np.count_nonzero(mask & numbered))
            block = pixels[y:y+h, x:x+w] & ~numbered
            denominator = int(mask.sum()+block.sum())
            score = float(2*np.count_nonzero(mask & block)/denominator) if denominator else 0.
            candidates.append((score, -overlap, x, y))
    if not candidates:
        raise ValueError('Bracket search is offscreen')
    if gap is not None:
        # Register the complete graphic, not just its longest horizontal
        # stroke. A one-pixel shift can improve aggregate Dice while cropping
        # a genuine hook. Every gate and the original +/-1 corridor still
        # apply to each candidate; an incomplete fit never authorizes a pass.
        for score, overlap, x, y in sorted(candidates, reverse=True):
            if (score >= .72 and -overlap <= max(2, mask.sum()*.02)
                    and _bracket_topology(pixels, mask, x, y, number_box, gap) is None):
                return score, x, y, -overlap
    score, overlap, x, y = max(candidates)
    return score, x, y, -overlap


@lru_cache(maxsize=1)
def _digit_glyphs():
    """Independent external-font rivals prevent a mostly-correct ratio pass."""
    import verovio
    resources = Path(verovio.__file__).resolve().parent/'data'
    metrics = ET.parse(resources/'Leipzig.xml').getroot()
    glyphs = {}
    for value in range(11):
        code = f'E{0x880+value:03X}'
        metric = metrics.find(f"g[@c='{code}']")
        x, y, w, h = (float(metric.get(k)) for k in ('x', 'y', 'w', 'h'))
        bounds = [x, -y-h, w, h]
        svg = ET.Element('svg', xmlns='http://www.w3.org/2000/svg',
                         viewBox=' '.join(map(str, bounds)), fill='white')
        svg.append(ET.parse(resources/'Leipzig'/f'{code}.xml').getroot())
        glyphs[code] = dict(svg=ET.tostring(svg, encoding='unicode'), bounds=bounds)
    return glyphs


def _digits(row, pixels, gap, nx, ny):
    number = row['number']
    glyphs = _digit_glyphs()
    result = []
    for code, part in zip(row['numeral_codes'], row['number_parts']):
        if part is None or code not in glyphs:
            raise ValueError('Reference numeral contains an unsupported or empty glyph')
        template = _resized_art(part, gap)
        x = nx+(part['bbox'][0]-number['bbox'][0])*gap/24
        y = ny+(part['bbox'][1]-number['bbox'][1])*gap/24
        (score, px, py), _ = _fit_mask(pixels, template, x, y, 1)
        bounds = glyphs[code]['bounds']
        origin_x, origin_y = px-bounds[0]*gap/250, py-bounds[1]*gap/250
        rivals = {other: match_glyph(pixels, glyph, gap, origin_x, origin_y,
                    centered=False, dxs=range(-1, 2), dys=range(-1, 2))
                  for other, glyph in glyphs.items() if other != code and (other != 'E88A' or code == 'E88A')}
        rival_code, rival = max(rivals.items(), key=lambda item: item[1], default=(None, 0.))
        result.append(dict(code=code, bbox=[px, py, px+template.shape[1], py+template.shape[0]],
                           match=round(score, 4), runner_up=round(rival, 4), runner_up_code=rival_code,
                           margin=round(score-rival, 4)))
    return result


def _tuplet(row, frames, target):
    events = row['events']
    number = row.get('number')
    ratios = {e['time_modification'] for e in events}
    if len(ratios) != 1 or None in ratios:
        raise ValueError('Tuplet source ratio is absent or inconsistent')
    actual, normal = next(iter(ratios))
    mark = row.get('mark')
    if mark is None:
        raise ValueError('Tuplet lacks a complete explicit source boundary')
    if mark[3] == 'none':
        raise ValueError('Hidden numeral has no independent pixel identity')
    digits = str(actual)+((':'+str(normal)) if mark[3] == 'both' else '')
    codes = [f'E{0x880+int(c):03X}' if c.isdigit() else 'E88A' for c in digits]
    if number is None or codes != row.get('numeral_codes'):
        return 'mismatch', 'Original numeral does not identify the written source ratio', dict(
            expected_numeral=digits, reference_codes=row.get('numeral_codes'))
    if mark[2] == 'yes' and row.get('bracket') is None:
        raise ValueError('Source-required bracket is absent from reference SVG')
    anchors = frames.anchors(events, target)
    frame = frames.frame(target)
    gap = anchors[0]['gap']
    scale = gap/24
    leaders = [i for i, event in enumerate(events) if not event['chord']]
    first, last = leaders[0], leaders[-1]
    ref_first = number['anchors'][first]
    ref_last = number['anchors'][last]
    x0, y0, x1, y1 = number['bbox']
    template = _resized_art(number, gap)
    # A singleton retains its genuine offset; a group number centres on
    # actual attack heads. No duration-derived second anchor is invented.
    if len(leaders) == 1:
        x = anchors[first]['x']+(x0-ref_first[0])*scale
    else:
        x = (anchors[first]['x']+anchors[last]['x'])/2-template.shape[1]/2
    y = anchors[first]['y']+(y0-ref_first[1])*scale
    if any(x <= column <= x+template.shape[1] for column in frame['occluded_columns']):
        raise ValueError('Measured coloured playhead occludes the source numeral')
    (score, nx, ny), margin = _fit_mask(frame['pixels'], template, x, y, math.ceil(gap*.5))
    if score < .79 or margin < .05:
        return 'mismatch', 'Actual numeral contour lacks the source identity or a unique bounded fit', dict(
            expected_numeral=digits, match=round(score, 4), margin=round(margin, 4))
    number_box = [nx, ny, nx+template.shape[1], ny+template.shape[0]]
    digit_evidence = _digits(row, frame['pixels'], gap, nx, ny)
    evidence = dict(expected_numeral=digits, numeral_match=round(score, 4), numeral_margin=round(margin, 4),
        digits=digit_evidence,
        number_bbox=number_box, anchors=anchors, staff_gap=gap,
        staff_lines=list(frame['staves'][events[0]['staff']].lines), bbox=number_box)
    if len(digit_evidence) != len(codes) or any(d['match'] < .79 or d['margin'] < .03 for d in digit_evidence):
        status = 'mismatch' if any(d['runner_up'] >= .79 and d['margin'] <= -.03 for d in digit_evidence) else 'ambiguous'
        return status, 'At least one numeral digit lacks independent source identity', evidence
    bracket = row.get('bracket')
    if bracket is not None:
        if len(leaders) == 1:
            source_x, actual_x = [ref_first[0]], [anchors[first]['x']]
        else:
            source_x = [ref_first[0], (x0+x1)/2, ref_last[0]]
            actual_x = [anchors[first]['x'], nx+template.shape[1]/2, anchors[last]['x']]
            if any(a >= b for a, b in zip(source_x, source_x[1:])) or any(a >= b for a, b in zip(actual_x, actual_x[1:])):
                raise ValueError('Bracket endpoints or numeral centre are not separately ordered')
        mask, box = _bracket_mask(bracket, source_x, actual_x, scale, ny-y0*scale)
        expected_columns = mask.any(axis=0)
        # Check the full permitted one-pixel fit corridor before fitting.
        # A playhead can erase an endpoint hook and make the best contour
        # shift away from that column. Checking only that fitted position
        # would then misreport occluded source ink as a detached hook.
        if any(0 <= x-box[0]+dx < mask.shape[1] and expected_columns[x-box[0]+dx]
               for x in frame['occluded_columns'] for dx in (-1, 0, 1)):
            raise ValueError('Measured coloured playhead occludes the bracket witness')
        fit, bx, by, overlapping_pixels = _fit_bracket(frame['pixels'], mask, box, template, number_box, gap)
        if overlapping_pixels > max(2, mask.sum()*.02):
            return 'ambiguous', 'Bracket and independently matched numeral silhouettes overlap', dict(
                **evidence, overlapping_pixels=overlapping_pixels, bracket_match=round(fit, 4))
        if fit < .72:
            return 'mismatch', 'Authentic bracket contour does not connect the source endpoint corridor', dict(
                **evidence, bracket_match=round(fit, 4), bracket_expected_bbox=box)
        # End hooks and every horizontal column must survive; a good global
        # Dice score alone could bless a missing short endpoint hook.
        h, w = mask.shape
        topology = _bracket_topology(frame['pixels'], mask, bx, by, number_box, gap)
        if topology is not None:
            return 'mismatch', topology, evidence
        bracket_box = [bx, by, bx+w, by+h]
        evidence.update(bracket_bbox=bracket_box, bracket_match=round(fit, 4),
            numeral_corridor_x=[round(nx-gap, 3), round(number_box[2]+gap, 3)],
            bbox=[min(nx, bx), min(ny, by), max(number_box[2], bx+w), max(number_box[3], by+h)])
    return 'verified', 'Original source numeral and bracket contours agree at actual PNG event anchors', evidence


def _verify(xml, folder, hand, reference_svgs, kind):
    if hand not in {'right', 'left', 'both'}:
        raise ValueError('Invalid hand')
    written = read_written_score(xml)
    folder = Path(folder)
    strings = tuple(reference_svgs) if reference_svgs is not None else tuple(
        path.read_text() for path in sorted(folder.glob('verovio-*.svg')))
    frames = CapturedFrames(folder, written)
    measured = []
    for row in _inventory(written, strings, kind, hand):
        events = row['events']
        record = dict(construct=kind, source_ids=[e['source']['id'] for e in events],
            event_ids=[e['id'] or e['source']['id'] for e in events],
            measure=events[0]['measure'] if events else None,
            staff=events[0]['staff'] if events else None,
            voice=events[0]['voice'] if events else None,
            beat=float(events[0]['beat']) if events else None,
            reference_group=row.get('group'), graphical=row.get('graphical', True),
            status='unverified', reason=row.get('error'), evidence={})
        if not row.get('error'):
            # Require source members in their own onset frames, and evaluate
            # actual connector ink in every common, visible group witness.
            witnesses = []
            failures = []
            targets = sorted({e['beat'] for e in row.get('leaders', events)})
            # Singleton numerals often cross the playhead at their onset.
            # A nearby saved frame can expose the original ink without
            # fabricating a second source event or renderer coordinate.
            targets += frames.nearby_clocks(targets)
            for target in targets:
                try:
                    status, reason, evidence = (_beam if kind == 'beam' else _tuplet)(row, frames, target)
                    witness = dict(frame=frames.frame(target)['name'], status=status, reason=reason, **evidence)
                    witnesses.append(witness)
                except (OSError, ValueError, KeyError, IndexError, AssertionError) as exc:
                    failures.append(dict(beat=float(target), reason=str(exc)))
            bad = next((w for w in witnesses if w['status'] != 'verified'), None)
            if bad:
                record.update(status=bad['status'], reason=bad['reason'], evidence=bad)
            elif witnesses:
                # A source-bound connector is often partly outside the
                # viewport at its first onset. Require independent valid
                # screenshot witnesses, but keep unusable frames visible in
                # the evidence rather than interpreting them as mismatches.
                record.update(status='verified', reason=witnesses[0]['reason'], evidence=dict(
                    **{k: v for k, v in witnesses[0].items() if k not in {'status', 'reason'}},
                    witnesses=witnesses, unavailable_witnesses=failures))
            else:
                record.update(reason='No unambiguous common PNG witness', evidence=dict(unavailable_witnesses=failures))
        measured.append(record)
    counts = Counter(r['status'] for r in measured)
    coverage = dict(expected=len(measured), **{s: counts[s] for s in STATUSES})
    return dict(measured=measured, coverage=coverage,
                complete=coverage['verified'] == coverage['expected'],
                scope='Independent source/XML and original SVG graphics; actual PNG anchors, rails and ink')


def verify_beam_pixels(xml: str, folder: Path, *, hand='both', reference_svgs=None) -> dict:
    return _verify(xml, folder, hand, reference_svgs, 'beam')


def verify_tuplet_pixels(xml: str, folder: Path, *, hand='both', reference_svgs=None) -> dict:
    return _verify(xml, folder, hand, reference_svgs, 'tuplet')

"""Bounded, source-directed evidence for note features in retained native PNGs.

Expected facts come exclusively from ``read_written_score(xml)``. Staff rails,
notehead registration and stem endpoints come from the current PNG. External
Verovio Leipzig outlines are read independently of application assets. Nothing
in fixture.json, native-overlay-report.json or a supplied pitch report supplies
geometry or authorizes a match. This is feature coverage, never a global proof
of engraving correctness or absence of extra ink.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

from . import phase3_pixels
from .pixel_proof import detect_staff_lines, expected_y
from .proof import read_written_score
from .raster_matching import (match_glyph, _joint_candidates,
                              glyph_search_components, match_glyphs_joint,
                              photographed_playhead_columns)
from .symbol_pixel_proof import bright, _outline

GLYPH_MINIMUM = .72
FAMILY_MARGIN = .05
HEAD_MINIMUM = .79
PITCH_TOLERANCE_STEPS = .42
STATUSES = ('verified', 'unverified', 'ambiguous', 'unsupported', 'mismatch')
FLAG_COUNTS = {'eighth': 1, '16th': 2, '32nd': 3, '64th': 4, '128th': 5}
ACCIDENTALS = {'flat': 'acc_flat', 'natural': 'acc_natural', 'sharp': 'acc_sharp',
               'double-flat': 'acc_double_flat', 'flat-flat': 'acc_double_flat',
               'double-sharp': 'acc_double_sharp'}
ALTERATIONS = {-2: 'double-flat', -1: 'flat', 0: 'natural', 1: 'sharp', 2: 'double-sharp'}


@lru_cache(maxsize=1)
def _feature_glyphs():
    """Extend the independent font reader, never the native atlas catalogue.

    Older Phase 3 checkouts exported ``_external_glyphs() -> dict``. The
    current checkout moved that API to reference_font.reference_glyphs.
    Both return {name: {svg, bounds, ...}} in 250 units per staff space.
    """
    from .reference_font import reference_glyphs
    import verovio

    reader = getattr(phase3_pixels, '_external_glyphs', reference_glyphs)
    result = dict(reader())
    resources = Path(verovio.__file__).resolve().parent / 'data'
    font = 'Leipzig'
    metrics = ET.parse(resources / f'{font}.xml').getroot()
    codes = {'augmentation_dot': 'E1E7', 'acc_flat': 'E260',
             'acc_natural': 'E261', 'acc_sharp': 'E262',
             'acc_double_sharp': 'E263', 'acc_double_flat': 'E264'}
    codes.update(clef_g='E050', clef_f='E062', clef_c='E05C')
    codes.update({f'time_{i}': f'{0xE080+i:04X}' for i in range(10)})
    for count in range(1, 6):
        for direction, offset in (('up', 0), ('down', 1)):
            codes[f'flag_{direction}_{count}'] = f'{0xE240 + 2*(count-1) + offset:04X}'
    for name, code in codes.items():
        metric = metrics.find(f"g[@c='{code}']")
        if metric is None or not (resources / font / f'{code}.xml').is_file():
            continue  # the caller retains this requirement as unsupported
        x, y, w, h = (float(metric.get(k)) for k in ('x', 'y', 'w', 'h'))
        bounds = [x-12, -y-h-12, w+24, h+24]
        svg = ET.Element('svg', xmlns='http://www.w3.org/2000/svg',
                         viewBox=' '.join(map(str, bounds)), fill='white')
        svg.append(ET.parse(resources / font / f'{code}.xml').getroot())
        result[name] = dict(svg=ET.tostring(svg, encoding='unicode'),
                            bounds=bounds, font=font, code=code)
    return result


def _result(status, reason, **evidence):
    return dict(status=status, reason=reason, evidence=evidence)


def _identity(note):
    return note.get('id') or note['source']['id']


def _marks(xml):
    """Supplement the oracle with explicit stem/adornment declarations only."""
    root = ET.fromstring(xml)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    result = {}
    for p, part in enumerate(root.findall('part')):
        for m, measure in enumerate(part.findall('measure')):
            for ordinal, element in enumerate(measure):
                if element.tag == 'note':
                    accidental = element.find('accidental')
                    result[f'xml-p{p}-m{m}-e{ordinal}'] = dict(
                        stem=element.findtext('stem'),
                        accidental_attributes={} if accidental is None else accidental.attrib)
    return result


def _accidentals(written):
    """Written accidental state, per measure/part/staff/pitch octave.

    Explicit cautionary naturals are requirements too. Implicit accidentals
    follow key and prior written spelling, across voices; tied continuations
    need no repeated accidental. Mid-measure changes are blocked by caller.
    """
    states = {}
    result = {}
    for note in written.symbols:
        if note['kind'] != 'note':
            continue
        staff, bar = note['staff'], note['index']
        keys = [(at, fifths) for at, hand, fifths in written.keys if hand == staff and at <= bar]
        fifths = max(keys, key=lambda pair: pair[0])[1] if keys else 0
        key_alters = {step: (1 if fifths > 0 else -1)
                      for step in ('FCGDAEB' if fifths > 0 else 'BEADGCF')[:abs(fifths)]}
        step, alter, octave = note['spelling']
        state = states.setdefault((note['part_index'], bar, staff), {})
        previous = state.get((step, octave), key_alters.get(step, 0))
        required = note['accidental']
        if required is None and not note['tie_stop'] and alter != previous:
            required = ALTERATIONS.get(alter, f'alteration-{alter}')
        result[note['source']['id']] = required
        state[step, octave] = alter
    return result


def _groups(notes):
    """Only actual source <chord/> declarations permit common feature ink."""
    groups, previous = [], None
    for note in notes:
        key = (note['part_index'], note['index'], note['staff'], note['voice'], note['beat'])
        if note['chord'] and previous == key:
            groups[-1].append(note)
        else:
            groups.append([note])
        previous = key
    return groups


def _register(pixels, staves, written, notes, glyphs, *, occlusion_columns=()):
    requests, heads, errors = [], {}, {}
    displaced=set()
    for group in _groups(notes):
        if len(group)>1:
            staff=staves[group[0]['staff']]
            ys=[expected_y(staff,n['spelling'],phase3_pixels._clef_at(written,n['index'],n['staff'])) for n in group]
            if any(0<abs(a-b)<=1.05*staff.gap for i,a in enumerate(ys) for b in ys[:i]):
                displaced.update(n['source']['id'] for n in group)
    ledgers={staff:phase3_pixels._ledger_context_rows(pixels,rail,written,
        [n for n in notes if n['staff']==staff]) for staff,rail in staves.items()}
    for note in notes:
        sid = note['source']['id']
        try:
            staff = staves[note['staff']]
            y = expected_y(staff, note['spelling'],
                          phase3_pixels._clef_at(written, note['index'], note['staff']))
            name = ('head_whole' if note['note_type'] == 'whole' else
                    'head_half' if note['note_type'] == 'half' else 'head_black')
            r = math.floor(PITCH_TOLERANCE_STEPS * staff.gap / 2)
            horizontal=math.ceil(1.5*staff.gap) if sid in displaced else 3
            requests.append(dict(note=note, glyph=glyphs[name], gap=staff.gap,
                                 origin_y=y, dxs=range(-horizontal,horizontal+1), dys=range(-r, r+1),
                                 alternatives=tuple((kind,glyphs[kind]) for kind in ('head_black','head_half','head_whole') if kind!=name),
                                 occlusion_columns=occlusion_columns,
                                 background_rows=ledgers[note['staff']] if name!='head_black' else ()))
        except (KeyError, ValueError, AssertionError, TypeError) as exc:
            errors[sid] = str(exc)
    origin = round(pixels.shape[1] * .42)
    for indices in glyph_search_components(requests, dys=range(0, 1)):
        group = [requests[i] for i in indices]
        registration = {}
        if len(group) == 1:
            candidates = _joint_candidates(pixels, group[0], origin, range(0, 1), HEAD_MINIMUM)
            assigned = candidates[:1] or None
        else:
            assigned = match_glyphs_joint(pixels, group, origin, dys=range(0, 1),
                                         minimum=HEAD_MINIMUM, diagnostics=registration)
        for i, request in enumerate(group):
            sid = request['note']['source']['id']
            if assigned is None:
                errors[sid] = ('Current-image notehead registration resource limit exhausted; no ownership verified'
                    if registration.get('exhausted') else
                    'Current-image notehead lacks a unique bounded .79 contour assignment')
                continue
            row = assigned[i]
            b, gap = request['glyph']['bounds'], request['gap']
            width, height = max(1, round(b[2]*gap/250)), max(1, round(b[3]*gap/250))
            heads[sid] = dict(x=row['x'] + b[2]*gap/500,
                              y=row['y'] - b[1]*gap/250,
                              bbox=[row['x'], row['y'], row['x']+width, row['y']+height],
                              score=row['score'], support=row['support'], gap=gap)
    return heads, errors


def _runs(values):
    indices = np.flatnonzero(values)
    if not len(indices):
        return []
    return [(int(a[0]), int(a[-1])+1) for a in np.split(indices, np.flatnonzero(np.diff(indices) > 1)+1)]


@lru_cache(maxsize=512)
def _reference_stem_extension(kind: str, intervals: tuple[int, ...], direction: str) -> float:
    """Ask Verovio about the same chord interval pattern in a neutral register.

    This is independently engraved from source intervals, never read from a
    native atlas. Verovio legitimately shortens stems for some chord/flag
    combinations; a universal three-space rule rejects its own engraving.
    """
    import verovio
    values = {'half': 2, 'quarter': 1, 'eighth': .5, '16th': .25,
              '32nd': .125, '64th': .0625, '128th': .03125}
    if kind not in values:
        raise ValueError('No independent stem reference for this written type')
    notes = []
    for i, offset in enumerate(intervals):
        octave, index = divmod(34+offset, 7)
        notes.append(f'<note id="ref{i}">' + ('<chord/>' if i else '') +
                     f'<pitch><step>{"CDEFGAB"[index]}</step><octave>{octave}</octave></pitch>'
                     f'<duration>{round(values[kind]*10080)}</duration><type>{kind}</type>' +
                     (f'<stem>{direction}</stem>' if not i else '') + '</note>')
    xml = ('<score-partwise version="4.0"><part-list><score-part id="P1">'
           '<part-name>Piano</part-name></score-part></part-list><part id="P1">'
           '<measure number="1"><attributes><divisions>10080</divisions>'
           '<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign>'
           '<line>2</line></clef></attributes>'+''.join(notes)+
           '</measure></part></score-partwise>')
    toolkit = verovio.toolkit()
    toolkit.setOptions({'breaks': 'none', 'header': 'none', 'footer': 'none', 'font': 'Leipzig'})
    if not toolkit.loadData(xml):
        raise ValueError('Independent chord stem reference failed to engrave')
    svg = ET.fromstring(toolkit.renderToSVG(1))
    ns = '{http://www.w3.org/2000/svg}'
    staff = next(n for n in svg.iter() if n.get('class') == 'staff')
    rails = [float(re.findall(r'-?[0-9.]+', n.get('d'))[1])
             for n in list(staff) if n.tag == ns+'path'][:5]
    gap = (max(rails)-min(rails))/4
    stem = next(n for n in staff.iter() if n.get('class') == 'stem')
    path = next(n for n in stem.iter() if n.tag == ns+'path')
    ends = list(map(float, re.findall(r'-?[0-9.]+', path.get('d'))))[1::2]
    ys = []
    for note in staff.iter():
        if note.get('id', '').startswith('ref') and note.get('class') == 'note':
            head = next(n for n in note.iter() if n.get('class') == 'notehead')
            use = next(n for n in head.iter() if n.tag == ns+'use')
            ys.append(float(re.search(r'translate\([^,]+,\s*([-0-9.]+)', use.get('transform')).group(1)))
    if len(ys) != len(intervals) or gap <= 0:
        raise ValueError('Independent chord stem/head accounting failed')
    return (min(ys)-min(ends))/gap if direction == 'up' else (max(ends)-max(ys))/gap


def _stem_runs_touch(first, second):
    """Adjacent continuous columns are one physical shaft, not two owners."""
    return any(abs(x-xx) <= 1 and max(top, yy) < min(bottom, end)
               for x, top, bottom in first for xx, yy, end in second)


def _stem_run_clusters(runs):
    remaining = list(runs)
    clusters = []
    while remaining:
        cluster = [remaining.pop(0)]
        while True:
            joined = [r for r in remaining if _stem_runs_touch(cluster, [r])]
            if not joined:
                break
            cluster.extend(joined)
            remaining = [r for r in remaining if r not in joined]
        clusters.append(sorted(cluster))
    return clusters


def _stem(pixels, group, heads, marks):
    ids = [_identity(n) for n in group]
    evidence = dict(group_id=group[0]['source']['id'], shared_source_ids=ids)
    if len(group) > 6:
        return _result('unsupported', 'Bounded stem grouping is limited to six source chord tones', **evidence)
    if any(n['source']['id'] not in heads for n in group):
        return _result('unverified', 'Every source chord head must first register in the current image', **evidence)
    hs = [heads[n['source']['id']] for n in group]
    gap = hs[0]['gap']
    directions = {marks[n['source']['id']]['stem'] for n in group} - {None}
    if directions - {'up', 'down'} or len(directions) > 1:
        return _result('unsupported', 'Conflicting, absent or specialized explicit stem declarations', **evidence)
    low, high = min(h['y'] for h in hs), max(h['y'] for h in hs)
    absolute = [int(n['spelling'][2])*7+'CDEFGAB'.index(n['spelling'][0]) for n in group]
    intervals = tuple(n-absolute[0] for n in absolute)
    candidates = []
    references = {}
    # Require an unbroken actual column attached to every source chord head.
    # Its minimum outer extension comes from independent Verovio engraving,
    # retaining a sub-step raster tolerance, rather than a fixed print length.
    for direction in directions or ('up', 'down'):
        try:
            extension = _reference_stem_extension(group[0]['note_type'], intervals, direction)
        except (ValueError, StopIteration, TypeError) as exc:
            return _result('unsupported', str(exc), **evidence)
        references[direction] = extension
        minimum = max(0, extension-.21)*gap
        sign = 1 if direction == 'up' else -1
        columns=None
        for h in hs:
            xs=[p % pixels.shape[1] for p in h['support']]
            # Seconds sit on opposite sides of their ONE shared stem.
            # Require the same actual column beside either edge of every
            # independently registered head; do not average displaced Xs.
            edges=(min(xs),max(xs)) if len(hs)>1 else ((max(xs) if sign==1 else min(xs)),)
            attached={x for edge in edges for x in range(edge-2,edge+3)}
            columns=attached if columns is None else columns & attached
        for x in sorted(columns):
            if not 0 <= x < pixels.shape[1]:
                continue
            for top, bottom in _runs(pixels[:, x]):
                if direction == 'up':
                    valid = low-8*gap <= top <= low-minimum and high-.5*gap <= bottom <= high+.5*gap
                else:
                    valid = low-.5*gap <= top <= low+.5*gap and high+minimum <= bottom <= high+8*gap
                if valid and all(top <= h['y'] <= bottom for h in hs):
                    candidates.append((direction, x, top, bottom))
    if not candidates:
        return _result('unverified', 'No continuous stem attached to every registered head with reference-supported extension',
                       **evidence, reference_extensions=references)
    options = []
    for direction in ('up', 'down'):
        for runs in _stem_run_clusters([c[1:] for c in candidates if c[0] == direction]):
            x = round(sum(c[0] for c in runs)/len(runs))
            top, bottom = min(c[1] for c in runs), max(c[2] for c in runs)
            bbox = [min(c[0] for c in runs), top, max(c[0] for c in runs)+1, bottom]
            options.append(_result('verified', 'Continuous pixel stem attaches the source chord heads',
                **evidence, bbox=bbox, direction=direction, x=x,
                tip_y=top if direction == 'up' else bottom-1,
                reference_extension_spaces=references[direction],
                head_matches=[round(h['score'], 4) for h in hs], shaft_runs=[list(r) for r in runs]))
    result = dict(options[0]) if len(options) == 1 else _result(
        'ambiguous', 'Multiple physical shafts or directions attach to this source group', **evidence)
    result['_shaft_options'] = options
    return result


def _stem_ownership(pixels, groups, heads, marks):
    """Assign physical shafts once, allowing only declared chords to share.

    A column may cross another voice's head. Joint ownership can still be
    unique when both voices have separate valid shafts. A single compound
    shaft touching several independent groups cannot certify just its lowest
    head while silently ignoring the other attached source obligations.
    """
    measured = [_stem(pixels, group, heads, marks) for group in groups]
    options = [(i, value) for i, result in enumerate(measured)
               for value in result.get('_shaft_options', [])]
    physical = []
    for i, value in options:
        runs = value['evidence']['shaft_runs']
        joined = [node for node in physical if _stem_runs_touch(runs, node['runs'])]
        node = dict(runs=list(runs), options=[(i, value)])
        for other in joined:
            node['runs'].extend(other['runs'])
            node['options'].extend(other['options'])
            physical.remove(other)
        node['runs'] = sorted(set(map(tuple, node['runs'])))
        physical.append(node)
    eligible = defaultdict(set)
    attachments = defaultdict(set)
    for index, node in enumerate(physical):
        for i, _value in node['options']:
            eligible[i].add(index)
            attachments[i].add(index)
        for i, group in enumerate(groups):
            for note in group:
                head = heads.get(note['source']['id'])
                if head is None or note['note_type'] in ('whole', 'breve', 'long', 'maxima'):
                    continue
                xs = [p % pixels.shape[1] for p in head['support']]
                if any(top <= head['y'] < bottom and
                       min(abs(x-min(xs)), abs(x-max(xs))) <= 2
                       for x, top, bottom in node['runs']):
                    attachments[i].add(index)
    remaining = set(attachments)
    while remaining:
        component, nodes = {min(remaining)}, set()
        while True:
            expanded = set().union(*(attachments[i] for i in component))
            neighbors = {i for i in remaining if attachments[i] & expanded}
            if neighbors <= component:
                nodes = expanded
                break
            component.update(neighbors)
        remaining.difference_update(component)
        def matching(forbidden=None):
            owners = {}

            def attach(i, seen):
                for node in sorted(eligible[i]):
                    if node in seen or forbidden == (i, node):
                        continue
                    seen.add(node)
                    if node not in owners or attach(owners[node], seen):
                        owners[node] = i
                        return True
                return False

            if all(attach(i, set()) for i in sorted(component)):
                return {i:node for node, i in owners.items()}
            return None

        assignment = matching()
        # Another complete assignment must omit at least one chosen edge.
        # Rechecking those edges avoids enumerating factorial permutations
        # when a dense full-performance onset has insufficient shafts.
        unique = assignment is not None and not any(
            matching((i, node)) is not None for i, node in assignment.items())
        for i in component:
            if unique:
                node_index = assignment[i]
                choices = [value for owner, value in physical[node_index]['options'] if owner == i]
                if len(choices) == 1:
                    measured[i] = deepcopy(choices[0])
                    runs = physical[node_index]['runs']
                    measured[i]['evidence']['physical_shaft_id'] = 'shaft:'+':'.join(map(str, (
                        min(r[0] for r in runs), min(r[1] for r in runs),
                        max(r[0] for r in runs)+1, max(r[2] for r in runs))))
                    continue
            evidence = dict(measured[i]['evidence'],
                competing_group_ids=[groups[j][0]['source']['id'] for j in sorted(component)],
                physical_shaft_count=len(nodes))
            measured[i] = _result('ambiguous',
                'Source groups do not have a unique assignment to separate physical stem shafts', **evidence)
    for result in measured:
        result.pop('_shaft_options', None)
    return measured


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


def _closed_component(pixels, row):
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


def _family(pixels, glyphs, names, expected, gap, x, y, dxs, dys, *, detached=False, centered=True,
            y_offsets=None):
    if expected not in glyphs or any(name not in glyphs for name in names):
        return _result('unsupported', 'External font lacks a required family outline', expected=expected)
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
        return _result('unverified', 'Insufficient authentic glyph contour at the bound feature position', **evidence)
    if name != expected:
        return _result('mismatch', 'A different authentic glyph family member has the strongest contour', **evidence)
    if score-runner < FAMILY_MARGIN:
        return _result('ambiguous', 'Authentic glyph family margin is below .05', **evidence)
    support = _closed_component(pixels, row) if detached else row['support']
    if support is None:
        return _result('ambiguous', 'Feature contour is connected to neighboring ink outside its own box', **evidence)
    result = _result('verified', 'Authentic external glyph passes .72 Dice and .05 family margin',
                     **evidence, bbox=row['bbox'])
    result['_support'] = support
    return result


@lru_cache(maxsize=128)
def _flag_origin_offset(name: str, gap: float) -> float:
    """Recover the attachment origin when flag ink prolongs the stem column.

    Downward 32nd and shorter Leipzig flags continue below their SMuFL
    origin. The bottom of visible continuous ink is therefore not the flag
    attachment. Read that continuation from the independent external mask.
    """
    glyph = _feature_glyphs()[name]
    b = glyph['bounds']
    mask = _outline(glyph['svg'], max(1, round(b[2]*gap/250)), max(1, round(b[3]*gap/250)))
    origin_x = round(-b[0]*gap/250)
    ys = np.nonzero(mask[:, max(0, origin_x-1):min(mask.shape[1], origin_x+2)])[0]
    if not len(ys):
        return 0.
    top, bottom = float(ys.min())+b[1]*gap/250, float(ys.max())+b[1]*gap/250
    return -min(0., top) if '_up_' in name else -max(0., bottom)


def _flag_absence(pixels, glyphs, heads, stem, associated_dots=None):
    """A quarter needs a visible, empty flag attachment, not a missing match.

    Read the attachment from the measured stem. Inspect both external flag
    families at that endpoint and require clear ink beside the stem, toward
    the outermost head of the source-declared common stem group. The entire
    chord has one attachment, not a separate search past each inner head.
    Unclassified/neighboring ink or clipping cannot prove absence.
    This is bounded attachment evidence, not a global extra-symbol check.
    """
    if stem['status'] != 'verified' or not heads or any(h is None for h in heads):
        return _result('unverified', 'Flag absence requires the independently registered head and stem')
    s, gap = stem['evidence'], heads[0]['gap']
    if len(heads) != len(s['shared_source_ids']) or any(abs(h['gap']-gap) > 1e-6 for h in heads):
        return _result('unverified', 'Every source common-stem head must have the same measured scale')
    boxes = [h['bbox'] for h in heads]
    head_box = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes)]
    names = tuple(f'flag_{d}_{c}' for d in ('up', 'down') for c in range(1, 6))
    if any(name not in glyphs for name in names):
        return _result('unsupported', 'External flag family is incomplete')
    scores = {name: match_glyph(pixels, glyphs[name], gap,
                  s['x']+(glyphs[name]['bounds'][0]+glyphs[name]['bounds'][2]/2)*gap/250,
                  s['tip_y']+_flag_origin_offset(name, gap), centered=True,
                  dxs=range(-2, 3), dys=range(-2, 3)) for name in names}
    # Both Leipzig flag directions put their off-shaft contour to the right
    # of the SMuFL origin. Stem direction changes the vertical range only.
    left, right = s['bbox'][2]+1, math.ceil(s['x']+1.6*gap)
    if s['direction'] == 'up':
        top, bottom = s['tip_y']-2, min(math.ceil(s['tip_y']+2.5*gap), head_box[1]-1)
    else:
        top, bottom = max(math.floor(s['tip_y']-2.5*gap), head_box[3]+1), s['tip_y']+3
    evidence = dict(expected_count=0, direction=s['direction'], stem_bbox=s['bbox'],
                    group_id=s['group_id'], shared_source_ids=s['shared_source_ids'],
                    head_bbox=head_box, head_bboxes=boxes, staff_gap=gap,
                    frame_size=[pixels.shape[1], pixels.shape[0]],
                    bbox=[left, top, right, bottom], family_scores=scores,
                    glyph_minimum=GLYPH_MINIMUM)
    if not (0 <= left < right <= pixels.shape[1] and 0 <= top < bottom <= pixels.shape[0]):
        return _result('unverified', 'Quarter flag attachment is clipped or inseparable from its head', **evidence)
    remaining=pixels[top:bottom,left:right].copy()
    raw=int(remaining.sum())
    associated=[]
    for sid,dots in (associated_dots or {}).items():
        if dots.get('status')!='verified' or not dots.get('_support'):
            continue
        changed=0
        for pixel in dots['_support']:
            y,x=divmod(pixel,pixels.shape[1])
            if top<=y<bottom and left<=x<right and remaining[y-top,x-left]:
                remaining[y-top,x-left]=False
                changed+=1
        if changed:
            associated.append(dict(source_id=sid,measurement=deepcopy(dots['evidence']),excluded_pixels=changed))
    ink=int(remaining.sum())
    evidence.update(bright_pixels=ink,raw_bright_pixels=raw,associated_dots=associated,
                    sampled_pixels=(right-left)*(bottom-top))
    if max(scores.values()) >= GLYPH_MINIMUM:
        return _result('mismatch', 'Quarter has an external-font flag contour at its measured stem endpoint', **evidence)
    if ink:
        return _result('unverified', 'Ink beside the quarter stem prevents independent flag absence', **evidence)
    return _result('verified', 'Visible quarter attachment is empty and every external flag contour is below threshold', **evidence)


def _accidental(pixels,glyphs,head,required,group_heads,context):
    """A source accidental precedes its chord and stays at its head's Y.

    Chord columns can spread freely to the left. A confidently identified
    intervening head prevents borrowing an earlier note's accidental.
    """
    gap=head['gap']
    leftmost=min(h['bbox'][0] for h in group_heads)
    width=glyphs[ACCIDENTALS[required]]['bounds'][2]*gap/250
    origin=head['x']-1.15*gap
    left=leftmost-max(4.,len(group_heads)+1.)*gap
    right=leftmost-.12*gap
    radius=max(1,math.floor(.12*gap))
    part=_family(pixels,glyphs,tuple(dict.fromkeys(ACCIDENTALS.values())),ACCIDENTALS[required],
        gap,origin,head['y'],range(math.ceil(left+width/2-origin),math.floor(right-width/2-origin)+1),
        range(-radius,radius+1),detached=True)
    if part['status']!='verified':
        return part
    box=part['evidence']['bbox']
    competing=[]
    for name in ('head_black','head_half','head_whole'):
        b=glyphs[name]['bounds']
        half=b[2]*gap/500
        dxs=range(math.ceil(box[2]+half-head['x']),math.floor(leftmost-half-head['x'])+1)
        if not dxs:
            continue
        request=dict(glyph=glyphs[name],gap=gap,origin_y=head['y'],dxs=dxs,dys=range(-1,2),
            alternatives=tuple((kind,glyphs[kind]) for kind in ('head_black','head_half','head_whole') if kind!=name),
            background_rows=context if name!='head_black' else ())
        candidates=_joint_candidates(pixels,request,head['x'],range(-1,2),HEAD_MINIMUM)
        if candidates:
            row=candidates[0]
            competing.append(dict(glyph=name,score=round(row['score'],4),bbox=[row['x'],row['y'],
                row['x']+round(b[2]*gap/250),row['y']+round(b[3]*gap/250)]))
    if competing:
        return _result('ambiguous','Another measured head lies between this accidental and its source chord',
                       **part['evidence'],competing_heads=competing)
    part['evidence'].update(head_bbox=head['bbox'],staff_gap=gap,
        clearance_spaces=(leftmost-box[2])/gap,vertical_tolerance_spaces=.12)
    return part


def _dot(pixels, glyphs, head, count):
    if count > 2:
        return _result('unsupported', 'More than two augmentation dots needs a separate bounded assignment', expected_count=count)
    gap, used, dots = head['gap'], set(), []
    for i in range(count):
        result = _family(pixels, glyphs, ('augmentation_dot',), 'augmentation_dot', gap,
                         head['x']+(1.15+i*.65)*gap, head['y']-.24*gap,
                         range(-6, 7), range(-5, 6), detached=True)
        if result['status'] != 'verified':
            return _result(result['status'], result['reason'], expected_count=count,
                           identified_dots=dots, candidate=result['evidence'])
        support = result.pop('_support')
        if used.intersection(support):
            return _result('ambiguous', 'Two source dots cannot reuse the same connected ink', expected_count=count)
        used.update(support)
        dots.append(result['evidence'])
    boxes = [r['bbox'] for r in dots]
    result = _result('verified', 'Every source dot has a separate isolated external-font contour',
                     expected_count=count, dots=dots,
                     bbox=[min(b[0] for b in boxes), min(b[1] for b in boxes),
                           max(b[2] for b in boxes), max(b[3] for b in boxes)])
    result['_support'] = frozenset(used)
    return result


def _chord_dots(pixels, glyphs, group, heads, rail, written):
    """Assign isolated dots to source chord tones in actual staff spaces.

    A displaced tone may share a column to the right of the full chord.
    Space tones retain their own space; line tones use an adjacent free
    space. A neighboring tone's dot cannot stand in for a missing one.
    """
    dotted=[n for n in group if n['dots']]
    output={}
    if any(n['source']['id'] not in heads for n in group):
        return {n['source']['id']:_result('unverified','All source chord heads must register before dot ownership') for n in dotted}
    gap=rail.gap
    positions={n['source']['id']:round((rail.bottom-expected_y(rail,n['spelling'],
        phase3_pixels._clef_at(written,n['index'],n['staff'])))*2/gap) for n in dotted}
    reserved={s for s in positions.values() if s%2}
    rightmost=max(heads[n['source']['id']]['x'] for n in group)
    choices={}
    for note in dotted:
        sid=note['source']['id']
        if note['dots']>4:
            output[sid]=_result('unsupported','More than four source dots needs another bounded assignment')
            continue
        head=heads[sid]
        step=positions[sid]
        targets=[step] if step%2 else [s for s in (step+1,step-1) if s not in reserved]
        if not targets:
            output[sid]=_result('unsupported','Dense chord dot lanes need an independent extended-space assignment')
            continue
        for index in range(note['dots']):
            options=[]
            for target in targets:
                part=_family(pixels,glyphs,('augmentation_dot',),'augmentation_dot',gap,
                    head['x']+(1.15+index*.65)*gap,rail.bottom-target*gap/2,
                    range(-round(.35*gap),round(rightmost-head['x']+.35*gap)+1),
                    range(-round(.28*gap),round(.28*gap)+1),detached=True)
                if part['status']=='verified' and not any(part['_support']==p['_support'] for p in options):
                    options.append(part)
            choices[sid,index]=options
    pending=[key for key,options in choices.items() if options]
    pending.sort(key=lambda key:len(choices[key]))
    visits=0
    def assign(index,used,found):
        nonlocal visits
        visits+=1
        if visits>10000:
            return None
        if index==len(pending):
            return found
        key=pending[index]
        for candidate in choices[key]:
            support=candidate['_support']
            if not used.intersection(support):
                result=assign(index+1,used|support,found | {key:candidate})
                if result is not None:
                    return result
        return None
    selected=assign(0,set(),{})
    for note in dotted:
        sid=note['source']['id']
        if sid in output:
            continue
        if selected is None or any((sid,i) not in selected for i in range(note['dots'])):
            output[sid]=_result('unverified','Every chord dot needs distinct isolated ink at its source staff space',expected_count=note['dots'])
            continue
        parts=[selected[sid,i] for i in range(note['dots'])]
        dots=[p['evidence'] for p in parts]
        boxes=[d['bbox'] for d in dots]
        output[sid]=_result('verified','Distinct external-font dots occupy source-compatible chord spaces',
            expected_count=note['dots'],dots=dots,
            bbox=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)])
        output[sid]['_support']=frozenset().union(*(p['_support'] for p in parts))
    return output


def _meter_sequence(pixels, glyphs, text, gap, origin_x, y, left_edge):
    """Classify observed digit locations first, then bind their written order.

    Family competition is local to one contour; another numeral anywhere in
    the header is not its runner-up. Each physical mark is consumed once,
    including repeated digits. Extra or inseparable marks remain blocking.
    """
    names = tuple(f'time_{i}' for i in range(10))
    if any(name not in glyphs for name in names):
        return [_result('unsupported', 'External meter digit family is incomplete')]
    dxs = range(max(-round(16*gap), math.ceil(left_edge-origin_x)), -round(.5*gap))
    dys = range(-max(1, round(.25*gap)), max(1, round(.25*gap))+1)
    candidates = []
    for name in names:
        request = dict(glyph=glyphs[name], gap=gap, origin_y=y, dxs=dxs)
        for candidate in _joint_candidates(pixels, request, origin_x, dys, GLYPH_MINIMUM):
            center = candidate['x']+glyphs[name]['bounds'][2]*gap/500
            candidates.append((candidate['score'], center, name, candidate['support']))
    observed, used, centers = [], set(), []
    for _, center, name, support in sorted(candidates, key=lambda c: -c[0]):
        if used.intersection(support) or any(abs(center-x) < .65*gap for x in centers):
            continue
        part = _family(pixels, glyphs, names, name, gap, center, y, range(-1, 2), dys)
        # Keep the independently winning family member even when the seed
        # candidate came from a competing shape at this same physical mark.
        winner = part.get('evidence', {}).get('observed')
        if part['status'] == 'mismatch' and winner in names:
            part = _family(pixels, glyphs, names, winner, gap, center, y, range(-1, 2), dys)
        claim = part.get('_support', support)
        if used.intersection(claim):
            return [_result('ambiguous', 'Meter digits cannot share observed contour ink')]
        used.update(claim)
        centers.append(center)
        observed.append((center, part))
    ordered = [part for _, part in sorted(observed, key=lambda p: p[0])]
    if len(ordered) != len(text):
        return [_result('unverified', 'Written meter digit count differs from independently located contours',
                        expected_text=text, observed_count=len(ordered))]
    for digit, part in zip(text, ordered):
        evidence = part.get('evidence', {})
        evidence['expected'] = 'time_'+digit
        if part['status'] == 'verified' and evidence.get('observed') != 'time_'+digit:
            part.update(status='mismatch', reason='Observed meter digit order differs from the source')
    return ordered


def _disjoint_meter_ink(checks, pixels, glyphs, gap):
    """Discard shared pixels from *all* identities, retaining full denominators.

    Adjacent numerator/denominator contours can touch. As in the existing
    joint head oracle, touching pixels cannot certify either identity; each
    remaining contour must still pass the original Dice and family margin.
    """
    counts = defaultdict(int)
    for part in checks:
        for pixel in part.get('_support', ()):
            counts[pixel] += 1
    for part in checks:
        support = part.pop('_support', None)
        if support is None or part['status'] != 'verified':
            continue
        unique = {pixel for pixel in support if counts[pixel] == 1}
        e = part['evidence']
        x0, y0, x1, y1 = e['bbox']
        template = _outline(glyphs[e['observed']]['svg'], x1-x0, y1-y0)
        denominator = int(template.sum())+int(pixels[y0:y1, x0:x1].sum())
        score = 2*len(unique)/denominator
        e.update(score=round(score, 4), margin=round(score-e['runner_up'], 4),
                 unique_ink_pixels=len(unique))
        if score < GLYPH_MINIMUM or score-e['runner_up'] < FAMILY_MARGIN:
            part.update(status='ambiguous', reason='Disjoint meter contour fails the unchanged Dice or family margin')


def _frame_shift(first, second):
    """Measure actual score translation without consulting native geometry.

    Retain the motion oracle's .80 full-contour agreement and minimum ink.
    The wider search permits retained frames several beats apart. Competing
    translations with the same evidence do not establish a source clock.
    """
    if first.size != second.size:
        return None
    a, b = bright(first), bright(second)
    if min(int(a.sum()), int(b.sum())) < 24:
        return None
    left, right = a.sum(axis=0).astype(float), b.sum(axis=0).astype(float)
    candidates = []
    for shift in range(-round(first.width*.75), round(first.width*.75)+1):
        aa, bb = (left[shift:], right[:-shift]) if shift > 0 else (
            (left[:shift], right[-shift:]) if shift < 0 else (left, right))
        norm = float(np.linalg.norm(aa)*np.linalg.norm(bb))
        candidates.append((float(aa.dot(bb))/norm if norm else 0, shift))
    measured = []
    for _, shift in sorted(candidates, reverse=True)[:8]:
        aa, bb = (a[:, shift:], b[:, :-shift]) if shift > 0 else (
            (a[:, :shift], b[:, -shift:]) if shift < 0 else (a, b))
        total = int(aa.sum())+int(bb.sum())
        dice = 2*int((aa & bb).sum())/total if total else 0.
        measured.append((dice, shift))
    score, shift = max(measured, key=lambda p: (p[0], -abs(p[1])))
    if score < .80 or any(s >= score-.02 and abs(x-shift) > 2 for s, x in measured):
        return None
    return dict(shift=shift, contour_agreement=score)


def _rule_tracks(picture, staves):
    """Ordinary dim rules span the complete grand staff, including its gap.

    Bright stems cannot substitute, even when one spans all five staff lines.
    A column group is one physical track; no nearby-column fallback is used.
    """
    rgb = np.asarray(picture).astype(float)
    structural = ((rgb.max(axis=2)-rgb.min(axis=2) < 40) &
                  (rgb.mean(axis=2) > 80) & ~bright(picture))
    top = round(min(staff.lines[0] for staff in staves.values()))+2
    bottom = round(max(staff.lines[-1] for staff in staves.values()))-2
    gap = min(staff.gap for staff in staves.values())
    return [(left, right) for left, right in _runs(structural[top:bottom].mean(axis=0) >= .90)
            if right-left <= max(2, .4*gap)]


def verify_structure_pixels(xml: str, folder: Path, elements: list[dict], *,
                            hand='both', first_bar=1) -> list[dict]:
    """Identify ordinary clefs, meters and measure rules in staff coordinates.

    Header X is searched freely before the timed music. Source XML declares
    the glyph identity; the screenshot supplies its scale and actual staff.
    Specialized signatures/barlines remain unsupported, never inferred from
    notehead or renderer metadata.
    """
    written, glyphs = read_written_score(xml), _feature_glyphs()
    result, rules, keys = [], {}, []
    clocks = sorted(float(path.stem.removeprefix('native-'))
                    for path in Path(folder).glob('native-*.png')
                    if re.fullmatch(r'native--?\d+\.\d+', path.stem))

    @lru_cache(maxsize=4)
    def frame(clock):
        with Image.open(Path(folder)/f'native-{clock:.5f}.png') as raw:
            picture = raw.convert('RGB')
        return picture, detect_staff_lines(picture)

    def boundary(clock, staff):
        key = clock, staff
        if key in rules:
            return rules[key]
        picture, staves = frame(clock)
        rail = staves[staff]
        value = _result('unverified', 'Boundary needs an independently registered source onset and coherent frame translation')
        for other_clock in sorted((c for c in clocks if abs(c-clock) > 1e-7), key=lambda c: abs(c-clock)):
            notes = [n for n in written.symbols if n['kind'] == 'note' and n['visible']
                     and abs(float(n['beat'])-other_clock) < 1e-7
                     and (hand == 'both' or n['staff'] == hand)]
            if not notes:
                continue
            other, other_staves = frame(other_clock)
            motion = _frame_shift(other, picture)
            if motion is None or motion['shift']*(clock-other_clock) <= 0:
                continue
            heads, _ = _register(bright(other), other_staves, written, notes, glyphs,
                                 occlusion_columns=photographed_playhead_columns(other))
            if len(heads) != len(notes):
                continue
            density = motion['shift']/(clock-other_clock)
            # The source onset's head is measured in the other PNG. Actual
            # frame displacement projects source times into this PNG, without
            # native-reported density, barline X, or print-spacing equality.
            anchor_x = sum(h['x'] for h in heads.values())/len(heads)
            endpoint = anchor_x+density*(clock-other_clock)-motion['shift']
            previous = [n for n in written.symbols if n['visible'] and float(n['beat']) < clock-1e-7]
            if not previous:
                value = _result('unverified', 'Opening rule has no preceding source interval to establish ownership')
                break
            last_beat = max(float(n['beat']) for n in previous)
            left = endpoint-density*(clock-last_beat)
            candidates = [(a, b) for a, b in _rule_tracks(picture, staves)
                          if left < (a+b-1)/2 < endpoint]
            evidence = dict(source_boundary_beat=clock, preceding_source_beat=last_beat,
                            source_interval_x=[left, endpoint], anchor_clock=other_clock,
                            anchor_source_ids=[_identity(n) for n in notes],
                            anchor_head_matches=[h['score'] for h in heads.values()],
                            motion=motion, staff_gap=rail.gap)
            if len(candidates) != 1:
                value = _result('unverified', 'Source boundary does not own one unique full-grand-staff rule track',
                                candidate_count=len(candidates), **evidence)
                break
            a, b = candidates[0]
            projected = (a+b-1)/2+motion['shift']
            witnesses = [(x, y) for x, y in _rule_tracks(other, other_staves)
                         if left+motion['shift'] < (x+y-1)/2 < endpoint+motion['shift']]
            if len(witnesses) != 1 or abs(sum(witnesses[0])/2-.5-projected) > 2:
                value = _result('unverified', 'The source-owned rule is missing or ambiguous at its motion-projected position', **evidence)
            else:
                value = _result('verified', 'Unique source-boundary rule retains its full grand-staff contour across actual score motion',
                                columns=list(range(a, b)), witness_columns=list(range(*witnesses[0])), **evidence)
            # A missing/ambiguous source-owned track cannot borrow another
            # line or retry a different reference frame to obtain a pass.
            break
        rules[key] = value
        return value

    for obligation in elements:
        kind, source = obligation['construct'], obligation['source']
        if kind == 'key':
            keys.append(obligation)
            continue
        if kind not in ('measure', 'barline', 'clef', 'meter'):
            continue
        index = int(source.get('measure_index', 1)) - (first_bar if source.get('origin') == 'original' else 1)
        row = dict(id=obligation['id'], construct=kind)
        try:
            if not 0 <= index < len(written.bars)-1:
                raise ValueError('Source measure does not correspond to captured window')
            start, end = float(written.bars[index]), float(written.bars[index+1])
            staff = source.get('staff')
            if staff not in ('right', 'left'):
                staff = hand if hand != 'both' else ('right' if source.get('part_index', 1) == 1 else 'left')
            picture, staves = frame(start)
            rail = staves[staff]
            details = source.get('details', {})
            if kind in ('measure', 'barline'):
                mark = ET.fromstring(details['xml']) if details.get('xml') else None
                style = mark.findtext('bar-style', 'regular') if mark is not None else 'regular'
                if mark is not None and (style not in ('regular', 'light') or mark.find('repeat') is not None):
                    proof = _result('unsupported', 'Specialized barline style requires its own pixel detector')
                else:
                    clock = start if mark is not None and mark.get('location') == 'left' else end
                    proof = boundary(clock, staff)
            elif kind == 'clef':
                mark = ET.fromstring(details['xml'])
                name = {'G': 'clef_g', 'F': 'clef_f', 'C': 'clef_c'}.get(mark.findtext('sign'))
                line = int(mark.findtext('line', '0'))
                if not name or not 1 <= line <= 5 or int(mark.findtext('clef-octave-change', '0')):
                    proof = _result('unsupported', 'Specialized/octave clef requires a bounded external-font detector')
                else:
                    y = rail.bottom-(line-1)*rail.gap
                    proof = _family(bright(picture), glyphs, ('clef_g', 'clef_f', 'clef_c'), name,
                        rail.gap, picture.width*.42, y,
                        range(-round(26*rail.gap), -round(rail.gap)),
                        range(-max(1, round(.2*rail.gap)), max(1, round(.2*rail.gap))+1))
            else:
                mark = ET.fromstring(details['xml'])
                numerator, denominator = mark.findtext('beats', ''), mark.findtext('beat-type', '')
                if not numerator.isdigit() or not denominator.isdigit() or mark.get('symbol') not in (None, 'normal'):
                    proof = _result('unsupported', 'Additive/symbolic meter requires its own independent glyph detector')
                else:
                    pixels = bright(picture)
                    sign, line, octave = phase3_pixels._clef_at(written, index, staff)
                    clef_name = {'G': 'clef_g', 'F': 'clef_f', 'C': 'clef_c'}.get(sign)
                    if not clef_name or octave:
                        raise ValueError('Meter ownership requires an independently identified ordinary clef')
                    clef = _family(pixels, glyphs, ('clef_g', 'clef_f', 'clef_c'), clef_name,
                        rail.gap, picture.width*.42, rail.bottom-(line-1)*rail.gap,
                        range(-round(26*rail.gap), -round(rail.gap)),
                        range(-max(1, round(.2*rail.gap)), max(1, round(.2*rail.gap))+1))
                    if clef['status'] != 'verified':
                        raise ValueError('Meter search cannot borrow digits from an unidentified clef/header')
                    left_edge = clef['evidence']['bbox'][2]
                    checks = []
                    boxes = []
                    for text, y in ((numerator, sum(rail.lines)/5-rail.gap),
                                    (denominator, sum(rail.lines)/5+rail.gap*.8)):
                        for part in _meter_sequence(pixels, glyphs, text, rail.gap,
                                                    picture.width*.42, y, left_edge):
                            box = part.get('evidence', {}).get('bbox')
                            if box:
                                boxes.append(box)
                            checks.append(part)
                    _disjoint_meter_ink(checks, pixels, glyphs, rail.gap)
                    proof = _result('verified' if all(c['status'] == 'verified' for c in checks) else 'unverified',
                        'Independent numerator and denominator glyphs on the actual staff', digits=checks, boxes=boxes)
            proof.pop('_support', None)
            if kind == 'meter':
                for child in proof.get('evidence', {}).get('digits', []):
                    child.pop('_support', None)
            row.update(proof)
        except (OSError, ValueError, KeyError, AssertionError, TypeError) as exc:
            row.update(_result('unverified', str(exc)))
        result.append(row)
    # Opening key signs belong between the independently located clef and
    # meter. A previous note's accidental cannot stand in for a missing key.
    # Changed keys need explicit cancellation/group ownership and remain
    # unsupported until that independent detector is available.
    obligations = {row['id']: row for row in elements}
    for obligation in keys:
        source = obligation['source']
        row = dict(id=obligation['id'], construct='key')
        try:
            index = int(source.get('measure_index', 1)) - (first_bar if source.get('origin') == 'original' else 1)
            if index != 0:
                raise ValueError('Changed key/cancellation group needs independent time-resolved ownership')
            staff = source['staff']
            picture, staves = frame(float(written.bars[index]))
            rail = staves[staff]
            clef = phase3_pixels._clef_at(written, index, staff)
            if clef not in (('G', 2, 0), ('F', 4, 0)):
                raise ValueError('Key placement for this clef needs an independent pattern')
            mark = ET.fromstring(source['details']['xml'])
            if mark.findtext('fifths') is None:
                raise ValueError('Nontraditional key signature needs its own glyph detector')
            fifths = int(mark.findtext('fifths'))
            if abs(fifths) > 7:
                raise ValueError('Extended key signature needs its own glyph detector')
            headers = [r for r in result if r['status'] == 'verified'
                       and obligations[r['id']]['source'].get('part_index') == source.get('part_index')
                       and obligations[r['id']]['source'].get('measure_index') == source.get('measure_index')]
            clefs = [r for r in headers if r['construct'] == 'clef']
            meters = [r for r in headers if r['construct'] == 'meter']
            if len(clefs) != 1 or len(meters) != 1:
                raise ValueError('Opening key requires independently identified adjacent clef and meter')
            left = clefs[0]['evidence']['bbox'][2]
            right = min(box[0] for box in meters[0]['evidence']['boxes'])
            origin = picture.width*.42
            dxs = range(round(left-origin), round(right-origin))
            pixels = bright(picture)
            if not fifths:
                observed = [match_glyph(pixels, glyphs[name], rail.gap, origin,
                            sum(rail.lines)/5, centered=True, dxs=dxs,
                            dys=range(-round(2*rail.gap), round(2*rail.gap)+1))
                            for name in ('acc_flat', 'acc_sharp', 'acc_natural')]
                proof = _result('verified' if max(observed) < GLYPH_MINIMUM else 'unverified',
                                'Opening C signature requires no key accidentals', observed_scores=observed)
            else:
                sharp = (('F', 5), ('C', 5), ('G', 5), ('D', 5), ('A', 4), ('E', 5), ('B', 4))
                flat = (('B', 4), ('E', 5), ('A', 4), ('D', 5), ('G', 4), ('C', 5), ('F', 4))
                pattern = sharp if fifths > 0 else flat
                shift = -2 if clef[0] == 'F' else 0
                checks, used = [], set()
                previous = -float('inf')
                for step_name, octave in pattern[:abs(fifths)]:
                    y = expected_y(rail, (step_name, 0, octave+shift), clef)
                    part = _family(pixels, glyphs, ('acc_flat', 'acc_sharp', 'acc_natural'),
                        'acc_sharp' if fifths > 0 else 'acc_flat', rail.gap, origin, y,
                        dxs, range(-max(1, round(.2*rail.gap)), max(1, round(.2*rail.gap))+1))
                    support = part.pop('_support', set())
                    box = part.get('evidence', {}).get('bbox')
                    center = (box[0]+box[2])/2 if box else -float('inf')
                    if part['status'] == 'verified' and (center <= previous or used.intersection(support)):
                        part = _result('unverified', 'Key signs must have distinct ordered contours')
                    previous = center
                    used.update(support)
                    checks.append(part)
                proof = _result('verified' if all(c['status'] == 'verified' for c in checks) else 'unverified',
                                'Opening key signs match source fifths in staff-relative order', signs=checks)
            row.update(proof)
        except (OSError, ValueError, KeyError, TypeError, AssertionError) as exc:
            row.update(_result('unsupported', str(exc)))
        result.append(row)
    return result


def verify_note_feature_pixels(xml: str, folder: Path, *, hand='both', pitch_report: dict | None = None) -> dict:
    """Measure every required stem/flag/dot/accidental at written onsets.

    ``xml`` is original source XML, or the independent quantization candidate
    for MIDI. Frames are ``native-{beat:.5f}.png``. ``pitch_report`` is an
    advisory compatibility argument: current PNG registration is always
    repeated, so stale/forged evidence cannot authorize a feature. No detector
    threshold is configurable. Missing/ambiguous/unsupported requirements
    remain in the denominator. Quarter flag absence has its own bounded
    attachment measurement. Beam masks and other extra-ink checks remain
    outside this API's scope.
    """
    if hand not in ('both', 'left', 'right'):
        raise ValueError('Invalid hand mode')
    folder = Path(folder)
    written, marks, glyphs = read_written_score(xml), _marks(xml), _feature_glyphs()
    accidentals = _accidentals(written)
    by_clock = defaultdict(list)
    for note in written.symbols:
        if note['kind'] == 'note' and note['visible']:
            by_clock[round(float(note['beat']), 8)].append(note)
    measured = []
    for beat, notes in sorted(by_clock.items()):
        rows = {}
        for note in notes:
            if hand != 'both' and note['staff'] != hand:
                continue
            features = {}
            kind = note['note_type']
            if kind not in ('whole', 'breve', 'long', 'maxima'):
                features['stem'] = _result('unverified', 'Current-image stem evidence required')
            if kind in FLAG_COUNTS and not note['beams'] or kind not in ('whole', 'breve', 'long', 'maxima', 'half', 'quarter', *FLAG_COUNTS):
                features['flag'] = _result('unverified', 'Current-image flag evidence required')
            if kind == 'quarter':
                features['flag_absence'] = _result('unverified', 'Current-image quarter flag absence required')
            if note['dots']:
                features['dot'] = _result('unverified', 'Current-image augmentation-dot evidence required')
            if accidentals[note['source']['id']]:
                features['accidental'] = _result('unverified', 'Current-image accidental evidence required')
            row = dict(source_id=_identity(note), measure=note['measure'], staff=note['staff'],
                       voice=note['voice'], beat=beat, spelling=note['spelling'], features=features)
            rows[note['source']['id']] = row
            measured.append(row)
        if not rows:
            continue
        filename = folder / f'native-{beat:.5f}.png'
        try:
            with Image.open(filename) as raw:
                image = raw.convert('RGB')
            staves, pixels = detect_staff_lines(image), bright(image)
        except (OSError, AssertionError, ValueError) as exc:
            for row in rows.values():
                for construct in row['features']:
                    row['features'][construct] = _result('unverified', f'Missing PNG or actual five-line staff evidence: {exc}', frame=filename.name)
            continue
        heads, errors = _register(pixels, staves, written, notes, glyphs,
                                  occlusion_columns=photographed_playhead_columns(image))
        groups = _groups(notes)
        owned_stems = _stem_ownership(pixels, groups, heads, marks)
        for group, stem in zip(groups, owned_stems):
            active = [n for n in group if n['source']['id'] in rows]
            if not active:
                continue
            if stem['status'] == 'verified':
                stem['evidence']['frame'] = filename.name
                stem['evidence']['physical_shaft_id'] = (
                    filename.name+':'+stem['evidence']['physical_shaft_id'])
            group_id = group[0]['source']['id']
            absence = None
            chord_dots=_chord_dots(pixels,glyphs,group,heads,staves[group[0]['staff']],written) if len(group)>1 else {
                n['source']['id']:_dot(pixels,glyphs,heads[n['source']['id']],n['dots'])
                for n in group if n['dots'] and n['source']['id'] in heads}
            if any(n['note_type'] == 'quarter' for n in active):
                absence = (_flag_absence(pixels, glyphs,
                    [heads.get(n['source']['id']) for n in group], stem,
                    {_identity(n):chord_dots[n['source']['id']] for n in group if n['source']['id'] in chord_dots})
                    if all(n['note_type'] == 'quarter' for n in group) else
                    _result('ambiguous', 'Mixed written types need separate common-stem flag ownership'))
            for note in active:
                sid, kind = note['source']['id'], note['note_type']
                features = rows[sid]['features']
                head = heads.get(sid)
                if 'stem' in features:
                    features['stem'] = dict(stem)
                if 'flag_absence' in features:
                    features['flag_absence'] = dict(absence)
                if 'flag' in features:
                    if kind not in FLAG_COUNTS:
                        features['flag'] = _result('unsupported', 'No bounded external flag detector for this written type', note_type=kind)
                    elif stem['status'] != 'verified':
                        features['flag'] = _result(stem['status'], 'A flag requires its own independently attached stem endpoint')
                    elif len({n['note_type'] for n in group}) != 1:
                        features['flag'] = _result('ambiguous', 'Mixed written types cannot share an identified flag')
                    else:
                        s = stem['evidence']
                        name = f"flag_{s['direction']}_{FLAG_COUNTS[kind]}"
                        features['flag'] = _family(pixels, glyphs,
                            tuple(f'flag_{d}_{c}' for d in ('up', 'down') for c in range(1, 6)),
                            name, head['gap'], s['x'], s['tip_y'],
                            range(-2, 3), range(-2, 3), centered=False,
                            y_offsets={f'flag_{d}_{c}': _flag_origin_offset(f'flag_{d}_{c}', head['gap'])
                                       for d in ('up', 'down') for c in range(1, 6)})
                        features['flag']['_group_id'] = group_id
                for construct in ('dot', 'accidental'):
                    if construct not in features:
                        continue
                    if head is None:
                        features[construct] = _result('unverified', errors.get(sid, 'Current-image head registration missing'))
                    elif construct == 'dot':
                        features[construct] = chord_dots[sid]
                    else:
                        required = accidentals[sid]
                        attrs = marks[sid]['accidental_attributes']
                        if required not in ACCIDENTALS or any(v == 'yes' for k, v in attrs.items() if k in ('parentheses', 'bracket')):
                            features[construct] = _result('unsupported', 'Accidental spelling/adornment needs an independent detector', expected=required)
                        else:
                            features[construct] = _accidental(pixels,glyphs,head,required,
                                [heads[n['source']['id']] for n in group if n['source']['id'] in heads],
                                phase3_pixels._ledger_context_rows(pixels,staves[note['staff']],written,group))
                # Mid-measure changes have no time-resolved clef/key API in
                # the existing pitch reader. Do not certify against a final
                # bar-level attribute when its onset order is ambiguous.
                changes = [m for structure in written.measures if structure['index'] == note['index']
                           and structure['source']['part_index'] == note['part_index']
                           for m in structure['metadata'] if m['kind'] in ('clef', 'key')
                           and float(m['onset']) > 0]
                if changes:
                    for construct in features:
                        features[construct] = _result('unsupported', 'Mid-measure clef/key changes require time-resolved registration')
        # Detached marks never reuse observed connected ink. Only a source
        # chord's explicitly common flag may share a contour.
        claims = [(name, result) for row in rows.values() for name, result in row['features'].items()
                  if result['status'] == 'verified' and '_support' in result]
        conflicted = set()
        for i, (name, result) in enumerate(claims):
            for j, (other_name, other) in enumerate(claims[:i]):
                common_flag = (name == other_name == 'flag' and
                               result.get('_group_id') == other.get('_group_id'))
                if not common_flag and result['_support'].intersection(other['_support']):
                    conflicted.update((i, j))
        for i in conflicted:
            claims[i][1].update(status='ambiguous', reason='Different source features cannot reuse the same observed ink')
        for row in rows.values():
            for result in row['features'].values():
                result.pop('_support', None)
                result.pop('_group_id', None)
    by_construct = {name: dict(expected=0, **dict.fromkeys(STATUSES, 0))
                    for name in ('stem', 'flag', 'dot', 'accidental', 'flag_absence')}
    for row in measured:
        for name, result in row['features'].items():
            by_construct[name]['expected'] += 1
            by_construct[name][result['status']] += 1
    coverage = {key: sum(c[key] for c in by_construct.values())
                for key in ('expected', *STATUSES)}
    complete = coverage['expected'] == coverage['verified']
    return dict(status='verified' if complete else 'incomplete', complete=complete,
                expected=coverage['expected'], verified=coverage['verified'], coverage=coverage,
                by_construct=by_construct, measured=measured,
                thresholds=dict(glyph_dice=GLYPH_MINIMUM, family_margin=FAMILY_MARGIN,
                                head_dice=HEAD_MINIMUM, pitch_staff_steps=PITCH_TOLERANCE_STEPS),
                pitch_report_rechecked=pitch_report is not None,
                scope='Required note features only, bound to current-image heads and original/candidate XML events',
                not_verified=['extra or unexpected symbols beyond the bounded quarter flag attachment',
                              'beams, ties, slurs, rests and key signatures',
                              'stem ownership where physical shafts or registered heads remain inseparable',
                              'global engraving correctness'])


def _ledger_segment(pixels, rail, head, step, context, occluded_columns):
    """Validate a physical rule; context rows alone never authorize ink."""
    gap = rail.gap
    expected = rail.bottom-step*gap/2
    left_head, _top, right_head, _bottom = head['bbox']
    extension = math.ceil(.12*gap)
    evidence = dict(step=step, expected_y=expected,
                    required_extension_spaces=.12, head_bbox=list(head['bbox']))
    if any(left_head-extension <= x < right_head+extension for x in occluded_columns):
        return dict(status='unverified', reason='Observed playhead covers required ledger ink', **evidence)
    left, right = max(0, left_head-round(2*gap)), min(pixels.shape[1], right_head+round(2*gap))
    if left > left_head-extension or right < right_head+extension:
        return dict(status='unverified', reason='Required ledger wings are offscreen', **evidence)

    def span(row):
        if not 0 <= row < pixels.shape[0]:
            return None
        # Deliberately do not merge the context detector's short gaps.
        return next(((left+a, left+b) for a, b in _runs(pixels[row, left:right])
                     if left+a <= left_head-extension and left+b >= right_head+extension), None)

    maximum = max(2, math.ceil(.14*gap))
    bands, seen = [], set()
    for row in sorted({y for y, _left, _right in context if abs(y-expected) <= .13*gap}):
        if row in seen or span(row) is None:
            continue
        top, bottom = row, row+1
        while row-top <= maximum and span(top-1) is not None:
            top -= 1
        while bottom-top <= maximum and span(bottom) is not None:
            bottom += 1
        seen.update(range(top, bottom))
        if bottom-top > maximum or abs((top+bottom-1)/2-expected) > .13*gap:
            continue
        spans = [span(y) for y in range(top, bottom)]
        a, b = max(s[0] for s in spans), min(s[1] for s in spans)
        bands.append(dict(bbox=[a, top, b, bottom], y=(top+bottom-1)/2,
            thickness_spaces=(bottom-top)/gap, continuous=True,
            left_extension_spaces=(left_head-a)/gap,
            right_extension_spaces=(b-right_head)/gap))
    if len(bands) != 1:
        return dict(status='ambiguous' if bands else 'mismatch',
            reason='No unique thin continuous ledger spans both registered head edges', **evidence)
    return dict(status='verified', reason='Actual thin continuous ledger extends beyond both head edges',
                **evidence, **bands[0])


def verify_ledger_pixels(xml: str, folder: Path, *, hand='both') -> dict:
    """Prove each source-required ledger step in actual PNGs, separately.

    Counts are line obligations; measured rows retain the existing per-note
    feature schema. No default feature counts or native metadata are used.
    Nearby frames expose ink hidden by the onset playhead. Their translation
    and current head family/assignment must both be independently measured.
    """
    from .connector_pixels import _Frames
    from .pixel_proof import RasterStaff

    if hand not in ('both', 'left', 'right'):
        raise ValueError('Invalid hand mode')
    written = read_written_score(xml)
    frames = _Frames(folder, written)
    unit_staff = RasterStaff('right', (0., 1., 2., 3., 4.), 1.)
    by_clock, measured = defaultdict(list), []
    for note in written.symbols:
        if note['kind'] != 'note' or not note['visible'] or (hand != 'both' and note['staff'] != hand):
            continue
        try:
            clef = phase3_pixels._clef_at(written, note['index'], note['staff'])
            step = round((unit_staff.bottom-expected_y(unit_staff, note['spelling'], clef))*2)
            steps = list(range(-2, step-1, -2) if step < 0 else range(10, step+1, 2))
            error = None
        except (ValueError, KeyError) as exc:
            steps, error = [], str(exc)
        changes = [m for structure in written.measures if structure['index'] == note['index']
                   and structure['source']['part_index'] == note['part_index']
                   for m in structure['metadata'] if m['kind'] == 'clef' and float(m['onset']) > 0]
        if changes:
            error = 'Mid-measure clef changes need time-resolved ledger expectations'
        if not steps and error is None:
            continue
        observation = dict(status='unsupported' if error else 'unverified',
            reason=error or 'Actual ledger ink required', expected_steps=steps, matched_segments=[], evidence={})
        row = dict(source_id=_identity(note), measure=note['measure'], staff=note['staff'], voice=note['voice'],
                   beat=float(note['beat']), spelling=note['spelling'], features=dict(ledger=observation))
        measured.append(row)
        if error is None:
            by_clock[note['beat']].append((note, row))
    glyphs = _feature_glyphs()
    for beat, required in by_clock.items():
        witnesses = defaultdict(list)
        # A dense sampling grid can put the four nearest frames inside the
        # same narrow playhead occlusion. Inspect more real neighboring
        # clocks; measured translation and a fully visible physical line
        # remain mandatory in every accepted witness.
        targets = [beat, *frames.nearby_clocks([beat], limit=12)]
        for target in targets:
            try:
                source_errors = {}
                for note, _row in required:
                    try:
                        frames.head(note)
                    except (ValueError, KeyError) as exc:
                        source_errors[note['source']['id']] = str(exc)
                frame = frames.frame(target)
                shift, registration = frames.shift(beat, target, required[0][0]['staff'])
                pixels = frame['pixels']
                if shift:
                    # Integer reindexing only: preserve every observed pixel
                    # while reusing the strict onset/chord head registration.
                    aligned = np.zeros_like(pixels)
                    if 0 < shift < pixels.shape[1]:
                        aligned[:, :-shift] = pixels[:, shift:]
                    elif -pixels.shape[1] < shift < 0:
                        aligned[:, -shift:] = pixels[:, :shift]
                else:
                    aligned = pixels
                notes = frames.notes_by_beat[beat]
                heads, errors = _register(aligned, frame['staves'], written, notes, glyphs)
                contexts = {staff: phase3_pixels._ledger_context_rows(aligned, rail, written,
                    [n for n in notes if n['staff'] == staff]) for staff, rail in frame['staves'].items()}
                for note, row in required:
                    sid = note['source']['id']
                    if sid in source_errors or sid not in heads:
                        witnesses[sid].append(dict(frame=frame['name'], status='unverified',
                            reason=source_errors.get(sid, errors.get(sid, 'Current-image head is unregistered'))))
                        continue
                    head, rail = heads[sid], frame['staves'][note['staff']]
                    segments = [_ledger_segment(aligned, rail, head, step, contexts[note['staff']],
                                frame['occluded_columns']-shift)
                                for step in row['features']['ledger']['expected_steps']]
                    for segment in segments:
                        if 'bbox' in segment:
                            segment['bbox'][0] += shift
                            segment['bbox'][2] += shift
                        segment['head_bbox'][0] += shift
                        segment['head_bbox'][2] += shift
                    status = next((s['status'] for s in segments if s['status'] != 'verified'), 'verified')
                    witnesses[sid].append(dict(frame=frame['name'], status=status, segments=segments,
                        head_bbox=[head['bbox'][0]+shift, head['bbox'][1], head['bbox'][2]+shift, head['bbox'][3]],
                        head_match=head['score'], staff_gap=rail.gap, staff_lines=list(rail.lines), registration=registration))
            except (OSError, ValueError, KeyError, AssertionError) as exc:
                for note, _row in required:
                    witnesses[note['source']['id']].append(dict(frame=f'native-{float(target):.5f}.png',
                        status='unverified', reason=str(exc)))
        for note, row in required:
            choices = witnesses[note['source']['id']]
            bad = next((w for w in choices if w['status'] == 'mismatch'), None)
            selected = bad or next((w for w in choices if w['status'] == 'verified'), choices[0])
            observation = row['features']['ledger']
            observation.update(status=selected['status'], reason=selected.get('reason',
                'Every source ledger step has actual ink' if selected['status'] == 'verified'
                else 'At least one required physical ledger is missing or unresolved'),
                matched_segments=[s for s in selected.get('segments', []) if s['status'] == 'verified'],
                evidence={**selected, 'witnesses': choices})
    coverage = dict(expected=0, **dict.fromkeys(STATUSES, 0))
    for row in measured:
        observation = row['features']['ledger']
        count = len(observation['expected_steps']) or 1
        verified = len(observation['matched_segments'])
        coverage['expected'] += count
        coverage['verified'] += verified
        coverage[observation['status']] += count-verified
    return dict(measured=measured, coverage=coverage, by_construct=dict(ledger=dict(coverage)),
        complete=all(r['features']['ledger']['status'] == 'verified' for r in measured),
        scope='Source-required physical ledger lines; current PNG heads and staff rails; no extra-line absence proof')

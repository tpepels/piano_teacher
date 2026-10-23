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
from functools import lru_cache
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

from . import phase3_pixels
from .pixel_proof import detect_staff_lines, expected_y
from .proof import read_written_score
from .raster_matching import (match_glyph, _joint_candidates,
                              glyph_search_components, match_glyphs_joint)
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


def _register(pixels, staves, written, notes, glyphs):
    requests, heads, errors = [], {}, {}
    for note in notes:
        sid = note['source']['id']
        try:
            staff = staves[note['staff']]
            y = expected_y(staff, note['spelling'],
                          phase3_pixels._clef_at(written, note['index'], note['staff']))
            name = ('head_whole' if note['note_type'] == 'whole' else
                    'head_half' if note['note_type'] == 'half' else 'head_black')
            r = math.floor(PITCH_TOLERANCE_STEPS * staff.gap / 2)
            requests.append(dict(note=note, glyph=glyphs[name], gap=staff.gap,
                                 origin_y=y, dxs=range(-3, 4), dys=range(-r, r+1)))
        except (KeyError, ValueError, AssertionError, TypeError) as exc:
            errors[sid] = str(exc)
    origin = round(pixels.shape[1] * .42)
    for indices in glyph_search_components(requests, dys=range(0, 1)):
        group = [requests[i] for i in indices]
        if len(group) == 1:
            candidates = _joint_candidates(pixels, group[0], origin, range(0, 1), HEAD_MINIMUM)
            assigned = candidates[:1] or None
        else:
            assigned = match_glyphs_joint(pixels, group, origin, dys=range(0, 1), minimum=HEAD_MINIMUM)
        for i, request in enumerate(group):
            sid = request['note']['source']['id']
            if assigned is None:
                errors[sid] = 'Current-image notehead lacks a unique bounded .79 contour assignment'
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


def _stem(pixels, group, heads, marks):
    ids = [_identity(n) for n in group]
    evidence = dict(group_id=group[0]['source']['id'], shared_source_ids=ids)
    if len(group) > 6:
        return _result('unsupported', 'Bounded stem grouping is limited to six source chord tones', **evidence)
    if any(n['source']['id'] not in heads for n in group):
        return _result('unverified', 'Every source chord head must first register in the current image', **evidence)
    hs = [heads[n['source']['id']] for n in group]
    gap = hs[0]['gap']
    if max(h['x'] for h in hs) - min(h['x'] for h in hs) > 3:
        return _result('ambiguous', 'Displaced chord heads need an independent stem attachment assignment', **evidence)
    directions = {marks[n['source']['id']]['stem'] for n in group} - {None}
    if directions - {'up', 'down'} or len(directions) > 1:
        return _result('unsupported', 'Conflicting, absent or specialized explicit stem declarations', **evidence)
    low, high = min(h['y'] for h in hs), max(h['y'] for h in hs)
    candidates = []
    # A normal stem extends at least three staff spaces from the outer head.
    # Require an unbroken actual column, attached to every registered chord
    # head, rather than counting arbitrary ink anywhere in a stem rectangle.
    for direction in directions or ('up', 'down'):
        sign = 1 if direction == 'up' else -1
        edge = sum((h['bbox'][2]-1 if sign == 1 else h['bbox'][0]) for h in hs) / len(hs)
        for x in range(round(edge)-2, round(edge)+3):
            if not 0 <= x < pixels.shape[1]:
                continue
            for top, bottom in _runs(pixels[:, x]):
                if direction == 'up':
                    valid = low-8*gap <= top <= low-3*gap and high-.5*gap <= bottom <= high+.5*gap
                else:
                    valid = low-.5*gap <= top <= low+.5*gap and high+3*gap <= bottom <= high+8*gap
                if valid and all(top <= h['y'] <= bottom for h in hs):
                    candidates.append((direction, x, top, bottom))
    if not candidates:
        return _result('unverified', 'No continuous stem attached to every registered head with three-space extension', **evidence)
    if len({c[0] for c in candidates}) != 1:
        return _result('ambiguous', 'Both stem directions have attached ink', **evidence)
    direction = candidates[0][0]
    x = round(sum(c[1] for c in candidates)/len(candidates))
    top = min(c[2] for c in candidates)
    bottom = max(c[3] for c in candidates)
    bbox = [min(c[1] for c in candidates), top, max(c[1] for c in candidates)+1, bottom]
    return _result('verified', 'Continuous pixel stem attaches the source chord heads',
                   **evidence, bbox=bbox, direction=direction, x=x,
                   tip_y=top if direction == 'up' else bottom-1,
                   head_matches=[round(h['score'], 4) for h in hs])


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


def _family(pixels, glyphs, names, expected, gap, x, y, dxs, dys, *, detached=False, centered=True):
    if expected not in glyphs or any(name not in glyphs for name in names):
        return _result('unsupported', 'External font lacks a required family outline', expected=expected)
    ranked = []
    for name in names:
        score, row = _locate(pixels, glyphs[name], gap, x, y, dxs, dys, centered=centered)
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


def verify_note_feature_pixels(xml: str, folder: Path, *, hand='both', pitch_report: dict | None = None) -> dict:
    """Measure every required stem/flag/dot/accidental at written onsets.

    ``xml`` is original source XML, or the independent quantization candidate
    for MIDI. Frames are ``native-{beat:.5f}.png``. ``pitch_report`` is an
    advisory compatibility argument: current PNG registration is always
    repeated, so stale/forged evidence cannot authorize a feature. No detector
    threshold is configurable. Missing/ambiguous/unsupported requirements
    remain in the denominator. Beam masks and absent-feature/extra-ink checks
    are outside this API's scope.
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
        heads, errors = _register(pixels, staves, written, notes, glyphs)
        groups = _groups(notes)
        counts = defaultdict(int)
        for group in groups:
            counts[group[0]['staff']] += 1
        for group in groups:
            active = [n for n in group if n['source']['id'] in rows]
            if not active:
                continue
            group_id = group[0]['source']['id']
            stem = _stem(pixels, group, heads, marks)
            if counts[group[0]['staff']] > 1:
                stem = _result('ambiguous', 'Simultaneous independent source voices need separate stem ownership', group_id=group_id)
            for note in active:
                sid, kind = note['source']['id'], note['note_type']
                features = rows[sid]['features']
                head = heads.get(sid)
                if 'stem' in features:
                    features['stem'] = dict(stem)
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
                            range(-2, 3), range(-2, 3), centered=False)
                        features['flag']['_group_id'] = group_id
                for construct in ('dot', 'accidental'):
                    if construct not in features:
                        continue
                    if head is None:
                        features[construct] = _result('unverified', errors.get(sid, 'Current-image head registration missing'))
                    elif construct == 'dot':
                        features[construct] = _dot(pixels, glyphs, head, note['dots'])
                    else:
                        required = accidentals[sid]
                        attrs = marks[sid]['accidental_attributes']
                        if required not in ACCIDENTALS or any(v == 'yes' for k, v in attrs.items() if k in ('parentheses', 'bracket')):
                            features[construct] = _result('unsupported', 'Accidental spelling/adornment needs an independent detector', expected=required)
                        else:
                            features[construct] = _family(pixels, glyphs,
                                tuple(dict.fromkeys(ACCIDENTALS.values())), ACCIDENTALS[required],
                                head['gap'], head['x']-1.15*head['gap'], head['y'],
                                range(-9, 10), range(-10, 11, 2), detached=True)
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
                    for name in ('stem', 'flag', 'dot', 'accidental')}
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
                not_verified=['extra or unexpected symbols and absent-feature assertions',
                              'beams, ties, slurs, rests and key signatures',
                              'dense/displaced or independent-voice stem ownership',
                              'global engraving correctness'])

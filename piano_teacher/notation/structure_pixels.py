"""Source-bound headers and measure rules measured from retained PNGs.

Each call owns its four-frame cache and boundary witnesses. Layout telemetry,
feature totals and other staffs' ink cannot establish a source obligation.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import math
from pathlib import Path
import re
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

from .feature_contract import GLYPH_MINIMUM, FAMILY_MARGIN, feature_result
from .feature_source import event_identity
from .glyph_evidence import measure_glyph_family
from .head_registration import register_noteheads
from .pixel_context import clef_at
from .pixel_ink import bright, rasterize_outline, pixel_runs
from .pixel_motion import frame_shift
from .pixel_proof import detect_staff_lines, expected_y
from .proof import read_written_score
from .raster_matching import match_glyph, _joint_candidates, photographed_playhead_columns
from .reference_font import feature_glyphs


def _meter_sequence(pixels, glyphs, text, gap, origin_x, y, left_edge):
    """Classify observed digit locations first, then bind their written order.

    Family competition is local to one contour; another numeral anywhere in
    the header is not its runner-up. Each physical mark is consumed once,
    including repeated digits. Extra or inseparable marks remain blocking.
    """
    names = tuple(f'time_{i}' for i in range(10))
    if any(name not in glyphs for name in names):
        return [feature_result('unsupported', 'External meter digit family is incomplete')]
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
        part = measure_glyph_family(pixels, glyphs, names, name, gap, center, y, range(-1, 2), dys)
        # Keep the independently winning family member even when the seed
        # candidate came from a competing shape at this same physical mark.
        winner = part.get('evidence', {}).get('observed')
        if part['status'] == 'mismatch' and winner in names:
            part = measure_glyph_family(pixels, glyphs, names, winner, gap, center, y, range(-1, 2), dys)
        claim = part.get('_support', support)
        if used.intersection(claim):
            return [feature_result('ambiguous', 'Meter digits cannot share observed contour ink')]
        used.update(claim)
        centers.append(center)
        observed.append((center, part))
    ordered = [part for _, part in sorted(observed, key=lambda p: p[0])]
    if len(ordered) != len(text):
        return [feature_result('unverified', 'Written meter digit count differs from independently located contours',
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
        template = rasterize_outline(glyphs[e['observed']]['svg'], x1-x0, y1-y0)
        denominator = int(template.sum())+int(pixels[y0:y1, x0:x1].sum())
        score = 2*len(unique)/denominator
        e.update(score=round(score, 4), margin=round(score-e['runner_up'], 4),
                 unique_ink_pixels=len(unique))
        if score < GLYPH_MINIMUM or score-e['runner_up'] < FAMILY_MARGIN:
            part.update(status='ambiguous', reason='Disjoint meter contour fails the unchanged Dice or family margin')


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
    return [(left, right) for left, right in pixel_runs(structural[top:bottom].mean(axis=0) >= .90)
            if right-left <= max(2, .4*gap)]


def verify_structure_pixels(xml: str, folder: Path, elements: list[dict], *,
                            hand='both', first_bar=1) -> list[dict]:
    """Identify ordinary clefs, meters and measure rules in staff coordinates.

    Header X is searched freely before the timed music. Source XML declares
    the glyph identity; the screenshot supplies its scale and actual staff.
    Specialized signatures/barlines remain unsupported, never inferred from
    notehead or renderer metadata.
    """
    written, glyphs = read_written_score(xml), feature_glyphs()
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
        value = feature_result('unverified', 'Boundary needs an independently registered source onset and coherent frame translation')
        for other_clock in sorted((c for c in clocks if abs(c-clock) > 1e-7), key=lambda c: abs(c-clock)):
            notes = [n for n in written.symbols if n['kind'] == 'note' and n['visible']
                     and abs(float(n['beat'])-other_clock) < 1e-7
                     and (hand == 'both' or n['staff'] == hand)]
            if not notes:
                continue
            other, other_staves = frame(other_clock)
            motion = frame_shift(other, picture)
            if motion is None or motion['shift']*(clock-other_clock) <= 0:
                continue
            heads, _ = register_noteheads(bright(other), other_staves, written, notes, glyphs,
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
                value = feature_result('unverified', 'Opening rule has no preceding source interval to establish ownership')
                break
            last_beat = max(float(n['beat']) for n in previous)
            left = endpoint-density*(clock-last_beat)
            candidates = [(a, b) for a, b in _rule_tracks(picture, staves)
                          if left < (a+b-1)/2 < endpoint]
            evidence = dict(source_boundary_beat=clock, preceding_source_beat=last_beat,
                            source_interval_x=[left, endpoint], anchor_clock=other_clock,
                            anchor_source_ids=[event_identity(n) for n in notes],
                            anchor_head_matches=[h['score'] for h in heads.values()],
                            motion=motion, staff_gap=rail.gap)
            if len(candidates) != 1:
                value = feature_result('unverified', 'Source boundary does not own one unique full-grand-staff rule track',
                                candidate_count=len(candidates), **evidence)
                break
            a, b = candidates[0]
            projected = (a+b-1)/2+motion['shift']
            witnesses = [(x, y) for x, y in _rule_tracks(other, other_staves)
                         if left+motion['shift'] < (x+y-1)/2 < endpoint+motion['shift']]
            if len(witnesses) != 1 or abs(sum(witnesses[0])/2-.5-projected) > 2:
                value = feature_result('unverified', 'The source-owned rule is missing or ambiguous at its motion-projected position', **evidence)
            else:
                value = feature_result('verified', 'Unique source-boundary rule retains its full grand-staff contour across actual score motion',
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
                    proof = feature_result('unsupported', 'Specialized barline style requires its own pixel detector')
                else:
                    clock = start if mark is not None and mark.get('location') == 'left' else end
                    proof = boundary(clock, staff)
            elif kind == 'clef':
                mark = ET.fromstring(details['xml'])
                name = {'G': 'clef_g', 'F': 'clef_f', 'C': 'clef_c'}.get(mark.findtext('sign'))
                line = int(mark.findtext('line', '0'))
                if not name or not 1 <= line <= 5 or int(mark.findtext('clef-octave-change', '0')):
                    proof = feature_result('unsupported', 'Specialized/octave clef requires a bounded external-font detector')
                else:
                    y = rail.bottom-(line-1)*rail.gap
                    proof = measure_glyph_family(bright(picture), glyphs, ('clef_g', 'clef_f', 'clef_c'), name,
                        rail.gap, picture.width*.42, y,
                        range(-round(26*rail.gap), -round(rail.gap)),
                        range(-max(1, round(.2*rail.gap)), max(1, round(.2*rail.gap))+1))
            else:
                mark = ET.fromstring(details['xml'])
                numerator, denominator = mark.findtext('beats', ''), mark.findtext('beat-type', '')
                if not numerator.isdigit() or not denominator.isdigit() or mark.get('symbol') not in (None, 'normal'):
                    proof = feature_result('unsupported', 'Additive/symbolic meter requires its own independent glyph detector')
                else:
                    pixels = bright(picture)
                    sign, line, octave = clef_at(written, index, staff)
                    clef_name = {'G': 'clef_g', 'F': 'clef_f', 'C': 'clef_c'}.get(sign)
                    if not clef_name or octave:
                        raise ValueError('Meter ownership requires an independently identified ordinary clef')
                    clef = measure_glyph_family(pixels, glyphs, ('clef_g', 'clef_f', 'clef_c'), clef_name,
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
                    proof = feature_result('verified' if all(c['status'] == 'verified' for c in checks) else 'unverified',
                        'Independent numerator and denominator glyphs on the actual staff', digits=checks, boxes=boxes)
            proof.pop('_support', None)
            if kind == 'meter':
                for child in proof.get('evidence', {}).get('digits', []):
                    child.pop('_support', None)
            row.update(proof)
        except (OSError, ValueError, KeyError, AssertionError, TypeError) as exc:
            row.update(feature_result('unverified', str(exc)))
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
            clef = clef_at(written, index, staff)
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
                proof = feature_result('verified' if max(observed) < GLYPH_MINIMUM else 'unverified',
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
                    part = measure_glyph_family(pixels, glyphs, ('acc_flat', 'acc_sharp', 'acc_natural'),
                        'acc_sharp' if fifths > 0 else 'acc_flat', rail.gap, origin, y,
                        dxs, range(-max(1, round(.2*rail.gap)), max(1, round(.2*rail.gap))+1))
                    support = part.pop('_support', set())
                    box = part.get('evidence', {}).get('bbox')
                    center = (box[0]+box[2])/2 if box else -float('inf')
                    if part['status'] == 'verified' and (center <= previous or used.intersection(support)):
                        part = feature_result('unverified', 'Key signs must have distinct ordered contours')
                    previous = center
                    used.update(support)
                    checks.append(part)
                proof = feature_result('verified' if all(c['status'] == 'verified' for c in checks) else 'unverified',
                                'Opening key signs match source fifths in staff-relative order', signs=checks)
            row.update(proof)
        except (OSError, ValueError, KeyError, TypeError, AssertionError) as exc:
            row.update(feature_result('unsupported', str(exc)))
        result.append(row)
    return result

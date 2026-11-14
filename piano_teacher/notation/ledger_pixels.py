"""Every source-required physical ledger line needs its own PNG witness.

One captured-frame owner belongs to one call. Reindexed pixels retain exact
support and strict registration; a known missing line dominates green frames.
"""
from __future__ import annotations

from collections import defaultdict
import math
from pathlib import Path

import numpy as np

from .captured_frames import CapturedFrames
from .feature_contract import STATUSES
from .feature_source import event_identity
from .head_registration import register_noteheads
from .pixel_context import clef_at, ledger_context_rows
from .pixel_ink import rasterize_outline, pixel_runs
from .pixel_proof import expected_y
from .proof import read_written_score
from .reference_font import feature_glyphs


def _ledger_visible_head(head, glyph):
    """Use the registered external silhouette's ink edges for ledger wings.

    Registration rectangles include the reference font's transparent padding.
    Keep that rectangle as ownership evidence, but do not require a physical
    ledger to extend beyond invisible pixels. Never derive the head edge from
    the observed union of head, ledger, stem or other neighboring ink.
    """
    left, top, right, bottom = head['bbox']
    rows, columns = np.nonzero(rasterize_outline(glyph['svg'], right-left, bottom-top))
    if not len(columns):
        raise ValueError('Registered external head has no visible outline')
    return dict(head, registration_bbox=list(head['bbox']),
                bbox=[left+int(columns.min()), top+int(rows.min()),
                      left+int(columns.max())+1, top+int(rows.max())+1])


def _ledger_segment(pixels, rail, head, step, context, occluded_columns):
    """Validate a physical rule; context rows alone never authorize ink."""
    gap = rail.gap
    expected = rail.bottom-step*gap/2
    left_head, _top, right_head, _bottom = head['bbox']
    extension = math.ceil(.12*gap)
    evidence = dict(step=step, expected_y=expected,
                    required_extension_spaces=.12, head_bbox=list(head['bbox']),
                    registration_bbox=list(head.get('registration_bbox', head['bbox'])))
    if any(left_head-extension <= x < right_head+extension for x in occluded_columns):
        return dict(status='unverified', reason='Observed playhead covers required ledger ink', **evidence)
    left, right = max(0, left_head-round(2*gap)), min(pixels.shape[1], right_head+round(2*gap))
    if left > left_head-extension or right < right_head+extension:
        return dict(status='unverified', reason='Required ledger wings are offscreen', **evidence)

    def span(row):
        if not 0 <= row < pixels.shape[0]:
            return None
        # Deliberately do not merge the context detector's short gaps.
        return next(((left+a, left+b) for a, b in pixel_runs(pixels[row, left:right])
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


def _dim_ledger_wings(dim_pixels, rail, head, step, occluded_columns):
    """Prove real subdued staff-colored ledger wings independently.

    The head masks cover the centre of a thin ledger; joining a dim mask
    with the pale notehead mask can certify an erased line. Require a
    continuous, measured horizontal wing on BOTH sides of the independently
    registered head, at exactly the written ledger step. An unrelated full
    staff rail (or a wide horizontal connector) cannot count as a short
    ledger: each physical run must end near its owning notehead.
    """
    gap = rail.gap
    expected = rail.bottom-step*gap/2
    left, _top, right, _bottom = head['bbox']
    extension = math.ceil(.12*gap)
    facts = dict(step=step, expected_y=expected,
        required_extension_spaces=.12, head_bbox=list(head['bbox']),
        registration_bbox=list(head.get('registration_bbox', head['bbox'])))
    if any(left-extension <= x < right+extension for x in occluded_columns):
        return dict(status='unverified', reason='Observed playhead covers required ledger ink', **facts)
    height, width = dim_pixels.shape
    reach = max(extension+2, math.ceil(1.5*gap))
    if left-extension < 0 or right+extension >= width:
        return dict(status='unverified', reason='Required ledger wings are offscreen', **facts)
    bands = []
    for y in range(max(0, round(expected-.13*gap)),
                   min(height, round(expected+.13*gap)+1)):
        lx0 = max(0,left-reach)
        rx1 = min(width,right+reach)
        left_runs = [(lx0+a,lx0+b) for a,b in pixel_runs(dim_pixels[y,lx0:left+1])]
        right_runs = [(right+a,right+b) for a,b in pixel_runs(dim_pixels[y,right:rx1])]
        # Allow one anti-aliased boundary pixel to be absent, but never an
        # interrupted outer wing. No interpolation or synthetic head bridge.
        good_left = [(a,b) for a,b in left_runs
                     if a <= left-extension and b >= left and b-a <= reach]
        good_right = [(a,b) for a,b in right_runs
                      if a <= right+1 and b >= right+extension and b-a <= reach]
        if len(good_left) == 1 and len(good_right) == 1:
            bands.append((y,good_left[0][0],good_right[0][1]))
    if not bands:
        return dict(status='mismatch',
            reason='No physically continuous subdued ledger wings on both sides of the head', **facts)
    groups=[]
    for y,a,b in bands:
        if not groups or y>groups[-1][-1][0]+1:
            groups.append([])
        groups[-1].append((y,a,b))
    candidates=[]
    for rows in groups:
        top,bottom=rows[0][0],rows[-1][0]+1
        centre=(top+bottom-1)/2
        if (bottom-top <= max(2,math.ceil(.14*gap)) and
                abs(centre-expected)<=.13*gap):
            a=min(row[1] for row in rows)
            b=max(row[2] for row in rows)
            candidates.append(dict(bbox=[a,top,b,bottom], y=centre,
                thickness_spaces=(bottom-top)/gap, continuous=True,
                left_extension_spaces=(left-a)/gap,
                right_extension_spaces=(b-right)/gap))
    if len(candidates)!=1:
        return dict(status='ambiguous' if candidates else 'mismatch',
            reason='Subdued ledger wings have no unique thin written row', **facts)
    return dict(status='verified',
        reason='Independent dim pixels form both source-required ledger wings',
        **facts, **candidates[0])

# This is a *local* source-ink proof. Captures from other measures can
# coincidentally register unrelated score ink after image translation, and
# such a spurious mismatch must not veto an independently verified ledger
# next to its source attack. Near misses still veto good photographs.
MAX_LEDGER_WITNESS_DISTANCE_BEATS = 1.25


def _ledger_witness_clocks(beat: float, frames: CapturedFrames) -> list[float]:
    """Only existing photographs near the source event can prove its ink.

    The onset frame is retained even when the fixed playhead obscures the
    ledger; subsequent captured clocks are examined in proximity order.
    Unlike unconstrained '12 nearest' sampling, this cannot reach another
    measure and misattribute its missing ink to the source note.
    """
    return [beat, *(clock for clock in frames.nearby_clocks([beat], limit=12)
                    if abs(clock-beat) <= MAX_LEDGER_WITNESS_DISTANCE_BEATS)]


def verify_ledger_pixels(xml: str, folder: Path, *, hand='both') -> dict:
    """Prove each source-required ledger step in actual PNGs, separately.

    Counts are line obligations; measured rows retain the existing per-note
    feature schema. No default feature counts or native metadata are used.
    Nearby frames expose ink hidden by the onset playhead. Their translation
    and current head family/assignment must both be independently measured.
    """
    from .pixel_proof import RasterStaff

    if hand not in ('both', 'left', 'right'):
        raise ValueError('Invalid hand mode')
    written = read_written_score(xml)
    frames = CapturedFrames(folder, written)
    unit_staff = RasterStaff('right', (0., 1., 2., 3., 4.), 1.)
    by_clock, measured = defaultdict(list), []
    for note in written.symbols:
        if note['kind'] != 'note' or not note['visible'] or (hand != 'both' and note['staff'] != hand):
            continue
        try:
            clef = clef_at(written, note['index'], note['staff'])
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
        row = dict(source_id=event_identity(note), measure=note['measure'], staff=note['staff'], voice=note['voice'],
                   beat=float(note['beat']), spelling=note['spelling'], features=dict(ledger=observation))
        measured.append(row)
        if error is None:
            by_clock[note['beat']].append((note, row))
    glyphs = feature_glyphs()
    for beat, required in by_clock.items():
        witnesses = defaultdict(list)
        # A dense sampling grid can put the nearest frames inside the
        # fixed playhead. Search more *local* real photographs; do not let
        # images from a distant measure create an unrelated veto mismatch.
        # Translated head registration and actual two-wing ink remain
        # mandatory for every accepted witness.
        targets = _ledger_witness_clocks(beat, frames)
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
                ledger_pixels = frame['ledger_ink']
                if shift:
                    # Bright head masks and the actual dim ledger wings are
                    # translated by the SAME independently measured motion.
                    aligned = np.zeros_like(pixels)
                    aligned_ledger = np.zeros_like(ledger_pixels)
                    if 0 < shift < pixels.shape[1]:
                        aligned[:, :-shift] = pixels[:, shift:]
                        aligned_ledger[:, :-shift] = ledger_pixels[:, shift:]
                    elif -pixels.shape[1] < shift < 0:
                        aligned[:, -shift:] = pixels[:, :shift]
                        aligned_ledger[:, -shift:] = ledger_pixels[:, :shift]
                else:
                    aligned = pixels
                    aligned_ledger = ledger_pixels
                notes = frames.notes_by_beat[beat]
                heads, errors = register_noteheads(aligned, frame['staves'], written, notes, glyphs,
                                                   playhead_x=frame['playhead_x'])
                bright_contexts = {staff: ledger_context_rows(aligned, rail, written,
                    [n for n in notes if n['staff'] == staff], playhead_x=frame['playhead_x'])
                    for staff, rail in frame['staves'].items()}
                for note, row in required:
                    sid = note['source']['id']
                    if sid in source_errors or sid not in heads:
                        witnesses[sid].append(dict(frame=frame['name'], status='unverified',
                            reason=source_errors.get(sid, errors.get(sid, 'Current-image head is unregistered'))))
                        continue
                    name = ('head_whole' if note['note_type'] == 'whole' else
                            'head_half' if note['note_type'] == 'half' else 'head_black')
                    head = _ledger_visible_head(heads[sid], glyphs[name])
                    rail = frame['staves'][note['staff']]
                    segments = []
                    bright_statuses = []
                    for step in row['features']['ledger']['expected_steps']:
                        # Preserve every previously certified pale-ledger
                        # witness. New dim-rail evidence is an alternative
                        # physical ink channel, never a veto over real bright
                        # wings or an excuse to relabel playhead occlusion.
                        bright_line = _ledger_segment(aligned, rail, head, step,
                            bright_contexts[note['staff']], frame['occluded_columns']-shift)
                        bright_statuses.append(bright_line['status'])
                        dim_line = _dim_ledger_wings(aligned_ledger, rail, head, step,
                            frame['occluded_columns']-shift)
                        if bright_line['status'] == 'verified':
                            segments.append(bright_line)
                        elif dim_line['status'] == 'verified':
                            segments.append(dim_line)
                        elif bright_line['status'] in ('unverified', 'mismatch'):
                            # A known missing physical pale wing dominates
                            # an ambiguous dark channel. Only independently
                            # PROVED dim wings can replace a pale mismatch.
                            segments.append(bright_line)
                        else:
                            segments.append(dim_line)
                    for segment in segments:
                        if 'bbox' in segment:
                            segment['bbox'][0] += shift
                            segment['bbox'][2] += shift
                        segment['head_bbox'][0] += shift
                        segment['head_bbox'][2] += shift
                        segment['registration_bbox'][0] += shift
                        segment['registration_bbox'][2] += shift
                    status = next((s['status'] for s in segments if s['status'] != 'verified'), 'verified')
                    bright_status = next((state for state in bright_statuses if state != 'verified'), 'verified')
                    witnesses[sid].append(dict(frame=frame['name'], status=status,
                        bright_status=bright_status, segments=segments,
                        head_bbox=[head['bbox'][0]+shift, head['bbox'][1], head['bbox'][2]+shift, head['bbox'][3]],
                        registration_bbox=[head['registration_bbox'][0]+shift, head['registration_bbox'][1],
                                           head['registration_bbox'][2]+shift, head['registration_bbox'][3]],
                        head_match=head['score'], staff_gap=rail.gap, staff_lines=list(rail.lines), registration=registration))
            except (OSError, ValueError, KeyError, AssertionError) as exc:
                for note, _row in required:
                    witnesses[note['source']['id']].append(dict(frame=f'native-{float(target):.5f}.png',
                        status='unverified', reason=str(exc)))
        for note, row in required:
            choices = witnesses[note['source']['id']]
            # A source that demonstrably has pale physical ledger lines in
            # another frame cannot silently switch to a weaker dim-only
            # witness in a damaged frame. Retain the original strict bright
            # mismatch as a veto. Consistently dim printed ink (Hanon)
            # remains eligible for the two-wing physical dim verifier.
            if any(w.get('bright_status') == 'verified' for w in choices):
                for witness in choices:
                    if (witness.get('status') == 'verified' and
                            witness.get('bright_status') not in (None, 'verified')):
                        witness['status'] = witness['bright_status']
                        witness['segments'] = []
                        witness['reason'] = 'An intact pale ledger in another photo conflicts with this dim-only witness'
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

"""Independent image measurements for the native continuous-repeat capture.

Only source MusicXML, public clock/density inputs and PNGs authorize evidence.
Renderer atlases, reported gap/staff positions and instance geometry are unused.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from piano_teacher.notation.feature_pixels import _feature_glyphs
from piano_teacher.notation.pixel_proof import detect_staff_lines, expected_y
from piano_teacher.notation.proof import read_written_score
from piano_teacher.notation.symbol_pixel_proof import _match_glyph
from piano_teacher.notation.phase3_pixels import verify_translation_sequence

DENSITY = 96.0
PLAYHEAD = .42


def repeat_expectations(data):
    """Read nominal opening meter independently; never use the terminal bar."""
    written = read_written_score(data['xml'])
    numerator, denominator = next(meter for index, meter in written.meter if index == 0)
    duration = float(written.bars[-1])
    gap = numerator * 4.0 / denominator
    return written, duration, gap


def notation_ink(image):
    # Dim inactive-hand notation must count too. Require a neutral foreground
    # brighter than every channel of the sampled actual background.
    rgb = np.asarray(image.convert('RGB')).astype(int)
    background = rgb[0, -1]
    return (rgb[:, :, 0] > background[0] + 42) & (rgb[:, :, 1] > background[1] + 32)


def verify_rest_frame(folder, data, frame):
    """An authentic whole rest hangs from the fourth rail on BOTH staves."""
    image = _load(folder, frame)
    staves = detect_staff_lines(image)
    ink = notation_ink(image)
    left, right = verify_gap_boundaries(folder, data, frame)
    x = (left + right) / 2
    glyphs = _feature_glyphs()
    measured = {}
    for hand, staff in staves.items():
        # Independent SMuFL restWhole outline has its origin at the rail it
        # hangs from, i.e. second rail from the top (not a freely searched Y).
        y = staff.lines[1]
        score, dx = max((_match_glyph(ink, glyphs['rest_whole'], staff.gap, x, y,
                                     centered=True, dxs=[dx], dys=range(-2, 3)), dx)
                        for dx in range(-2, 3))
        assert score >= .80, (f"{frame['name']} {hand}: missing authentic centered "
                               f"whole-measure rest ({score:.3f})")
        measured[hand] = {'x': x + dx, 'y': y, 'score': score}
    return measured


def _load(folder, frame):
    path = Path(folder) / frame['base']
    assert path.is_file(), f'Missing native framebuffer: {path}'
    with Image.open(path) as raw:
        image = raw.convert('RGB')
    assert image.size == (1536, 520), 'Expected actual 1536x520 native framebuffer'
    return image


def _boundaries(image, duration, gap, clock):
    return [image.width * PLAYHEAD + (beat - clock) * DENSITY
            for beat in (duration, duration + gap)]


def verify_gap_boundaries(folder, data, frame):
    """Recover complete strokes in the conventional pre-onset clearance band.

    The source onsets keep exact beat X. A barline precedes the incoming
    notehead, so engraved measure width is not the semantic pause duration.
    """
    _, duration, gap = repeat_expectations(data)
    image = _load(folder, frame)
    staves = detect_staff_lines(image)
    ink = notation_ink(image)
    top = round(staves['right'].lines[0])
    bottom = round(staves['left'].lines[-1])
    observed = []
    for side, x in zip(('start', 'end'), _boundaries(image, duration, gap, frame['clock'])):
        assert 3 <= x < image.width - 3, 'Capture must include both practice boundaries'
        candidates = [(float(ink[top:bottom + 1, col].mean()), col)
                      for col in range(round(x - 2 * staves['right'].gap), round(x) + 2)]
        complete = [col for coverage, col in candidates if coverage >= .97]
        clusters = []
        for col in complete:
            if not clusters or col - clusters[-1][-1] > 1:
                clusters.append([col])
            else:
                clusters[-1].append(col)
        assert len(clusters) == 1, (f"{frame['name']}: {side} boundary missing or detached "
                                    f"from full grand staff near beat x={x:.2f} ({complete})")
        observed.append(float(np.mean(clusters[0])))
    # Incoming noteheads occupy roughly half a staff space either side of
    # their musical anchor; a structural stroke must clear that ink.
    incoming_x = _boundaries(image, duration, gap, frame['clock'])[1]
    assert incoming_x - observed[1] >= .7 * staves['left'].gap, 'End boundary crosses incoming notehead'
    assert observed[0] < observed[1], 'Preparation barlines are reversed'
    return observed


def verify_clean_gap(folder, data, frame, report):
    """Account for all gap ink: two rests, rails and the two boundary strokes."""
    image = _load(folder, frame)
    staves = detect_staff_lines(image)
    left, right = verify_gap_boundaries(folder, data, frame)
    left, right = round(left) + 4, round(right) - 3
    ink = notation_ink(image).copy()
    center = sum(verify_gap_boundaries(folder, data, frame)) / 2
    rest = _feature_glyphs()['rest_whole']['bounds']
    for staff in staves.values():
        unit = staff.gap / 250
        x0 = round(center - rest[2] * unit / 2) - 3
        x1 = x0 + round(rest[2] * unit) + 6
        y0 = round(staff.lines[1] + rest[1] * unit) - 3
        y1 = y0 + round(rest[3] * unit) + 6
        ink[y0:y1, x0:x1] = False
        # Remove only the photographed rail strokes, never arbitrary symbols.
        for rail in staff.lines:
            ink[round(rail) - 1:round(rail) + 2, left:right] = False
    # Check above and below both staves too: a floated meter is still extra ink.
    top = max(0, round(staves['right'].lines[0] - 4 * staves['right'].gap))
    bottom = min(image.height, round(staves['left'].lines[-1] + 3 * staves['left'].gap))
    extra = int(ink[top:bottom, left:right].sum())
    assert extra <= 8, f"{frame['name']}: unexpected clef/key/time or other gap ink ({extra} pixels)"

    rgb = np.asarray(image).astype(float)
    luminance = rgb.max(axis=2)
    columns = np.arange(left, right)
    # Whole-rest ink touches its supporting rail; inspect unoccluded staff.
    columns = columns[abs(columns - center) > 1.2 * staves['right'].gap]
    for hand, staff in staves.items():
        for rail in staff.lines:
            y = round(rail)
            peak = luminance[y - 1:y + 2, columns].max(axis=0)
            shoulder = (luminance[y - 5, columns] + luminance[y + 5, columns]) / 2
            assert float(np.mean(peak - shoulder >= 5)) >= .96, f'{hand}: broken staff rail across rest'
    return extra


def verify_repeat_motion(folder, data, report):
    frames = {frame['name']: frame for frame in report['frames']}
    images = [_load(folder, frames[name]) for name in ('rest-before', 'rest', 'rest-after')]
    result = verify_translation_sequence(*images)
    assert result['passed'], f'Noncontinuous repeat motion: {result}'
    assert result['pixel_steps'] == [12, 12], f'Expected public 96 * .125 pixel movement: {result}'
    return result


def verify_next_source_arrival(folder, data, report):
    """Derive the first real attack q from XML and register it at D+G+q.

    This is the timing proof. Barline-to-barline engraving width is allowed
    conventional notehead clearance and cannot authorize a different stride.
    """
    written, duration, gap = repeat_expectations(data)
    hand = data.get('hand', 'both')
    attacks = [event for event in written.symbols
               if event['kind'] == 'note' and not event.get('tie_stop')
               and (hand == 'both' or event['staff'] == hand)]
    assert attacks, 'Focused repeat fixture must contain a real source attack'
    onset = min(float(event['beat']) for event in attacks)
    name = 'repeat-arrival' if onset > 0 else 'repeat'
    frame = next(item for item in report['frames'] if item['name'] == name)
    assert abs(frame['clock'] - duration - gap - onset) < 1e-7, 'Wrong next-source clock'
    image = _load(folder, frame)
    staves = detect_staff_lines(image)
    ink = notation_ink(image)
    glyphs = _feature_glyphs()
    heads = []
    for event in attacks:
        if float(event['beat']) != onset or event.get('chord'):
            continue
        staff = staves[event['staff']]
        clef = _context(written, 0, event['staff'])[2]
        y = expected_y(staff, tuple(event['spelling']), clef)
        kind = event['note_type'] if event['note_type'] in ('whole', 'half') else 'black'
        score = _match_glyph(ink, glyphs[f'head_{kind}'], staff.gap,
                             image.width * PLAYHEAD, y, centered=True,
                             dxs=range(-2, 3), dys=range(-2, 3))
        assert score >= .79, (f"Incoming {event['staff']} source head misses D+G+q playhead "
                               f"({score:.3f}); pause duration or source position changed")
        heads.append({'source_id': event['source']['id'], 'staff': event['staff'],
                      'score': score, 'clock': frame['clock']})
    assert heads, 'First real source attack needs an independently measurable head'
    return heads


def _context(written, index, hand):
    meter = next(value for at, value in reversed(written.meter) if at <= index)
    key = next((value for at, staff, value in reversed(written.keys)
                if at <= index and staff == hand), 0)
    clef = next(((sign, line, octave) for at, staff, sign, line, octave in reversed(written.clefs)
                 if at <= index and staff == hand), ('G', 2, 0) if hand == 'right' else ('F', 4, 0))
    return tuple(meter), key, clef


def _glyph_hits(ink, glyph, staff, interval, origin_y):
    """Search external font outlines in a source-directed header interval."""
    lo, hi = map(round, interval)
    width = glyph['bounds'][2] * staff.gap / 250
    scores = []
    for x in range(max(round(width / 2) + 1, lo), min(ink.shape[1] - round(width / 2) - 1, hi), 2):
        value = _match_glyph(ink, glyph, staff.gap, x, origin_y,
                             centered=True, dxs=range(-1, 2),
                             dys=range(-max(2, round(staff.gap / 4)), max(2, round(staff.gap / 4)) + 1))
        if value >= .80:
            scores.append((value, x))
    hits = []
    for score, x in sorted(scores, reverse=True):
        if all(abs(x - hit['x']) > width * .55 for hit in hits):
            hits.append({'x': x, 'score': score})
    return sorted(hits, key=lambda item: item['x'])


def verify_context_headers(folder, data, report):
    """Opening, source-internal changes and restoration before GAP START."""
    written, duration, gap = repeat_expectations(data)
    frames = {frame['name']: frame for frame in report['frames']}
    glyphs = _feature_glyphs()
    obligations = [(0, 'opening', 0.0, True)]
    for index in range(1, len(written.bars) - 1):
        if any(_context(written, index - 1, hand) != _context(written, index, hand)
               for hand in ('right', 'left')):
            # The fixture includes dedicated internal clocks for changes beyond
            # the opening viewport; do not silently omit off-screen changes.
            name = f'change-{index}' if f'change-{index}' in frames else 'opening'
            obligations.append((index, name, float(written.bars[index]), False))
    if any(_context(written, len(written.bars) - 2, hand) != _context(written, 0, hand)
           for hand in ('right', 'left')):
        obligations.append((0, 'rest', duration, False))
    evidence = []
    for index, name, beat, opening in obligations:
        image = _load(folder, frames[name])
        ink = notation_ink(image)
        staves = detect_staff_lines(image)
        end = image.width * PLAYHEAD + (beat - frames[name]['clock']) * DENSITY
        restoration_rule = verify_gap_boundaries(folder, data, frames[name])[0] if name == 'rest' else None
        previous_index = len(written.bars) - 2 if beat == duration else index - 1
        for hand, staff in staves.items():
            meter, key, clef = _context(written, index, hand)
            previous = None if opening else _context(written, previous_index, hand)
            interval = (end - 19 * staff.gap, end - .4 * staff.gap)
            assert interval[0] >= 0 and end < image.width, 'Context change needs a complete framebuffer'
            middle = (staff.lines[0] + staff.lines[-1]) / 2
            # Gray rules add false silhouette pixels across tall signatures.
            # Separate their observed row color from this staff's observed
            # notation color, including the genuinely dim inactive hand.
            red = np.asarray(image)[:, :, 0]
            lo, hi = map(round, interval)
            region = red[max(0, round(middle - 4 * staff.gap)):
                         min(image.height, round(middle + 4 * staff.gap)), lo:hi]
            foreground = float(np.percentile(region, 99.5))
            rail_color = max(float(np.median(red[round(y) - 1:round(y) + 2], axis=1).max())
                             for y in staff.lines)
            header_ink = ink & (red > (foreground + rail_color) / 2)
            def find(glyph_name, y):
                target = glyphs[glyph_name]
                search = interval
                if restoration_rule is not None:
                    half_width = target['bounds'][2] * staff.gap / 500
                    search = (interval[0], min(interval[1], restoration_rule - half_width - 1))
                return _glyph_hits(header_ink, target, staff, search, y)
            if opening or clef != previous[2]:
                origin = staff.lines[-1] - (clef[1] - 1) * staff.gap
                hits = find({'G': 'clef_g', 'F': 'clef_f', 'C': 'clef_c'}[clef[0]], origin)
                assert hits, f'{name} {hand}: missing real clef change before beat {beat}'
                evidence.append({'frame': name, 'hand': hand, 'kind': 'clef', 'hits': hits})
            if opening or meter != previous[0]:
                for number, y in ((meter[0], middle - staff.gap), (meter[1], middle + staff.gap)):
                    assert 0 <= number <= 9, 'Focused repeat fixture uses single-digit meter'
                    hits = find(f'time_{number}', y)
                    assert hits, f'{name} {hand}: missing {number} meter digit before beat {beat}'
                    evidence.append({'frame': name, 'hand': hand, 'kind': 'meter', 'hits': hits})
            if opening or key != previous[1]:
                # Search only the standard signature vertical range. Key
                # changes in these fixtures use +1/-2, with authentic naturals
                # required when cancelling the previous opposite signature.
                kinds = []
                if key:
                    kinds.append(('acc_sharp' if key > 0 else 'acc_flat', abs(key)))
                if previous and previous[1] and (key * previous[1] <= 0):
                    kinds.append(('acc_natural', abs(previous[1])))
                for kind, count in kinds:
                    found = []
                    for y in np.arange(staff.lines[0] - staff.gap, staff.lines[-1] + staff.gap / 2, staff.gap / 2):
                        for hit in find(kind, y):
                            if all(abs(hit['x'] - item['x']) > staff.gap * .5 for item in found):
                                found.append(hit)
                    assert len(found) >= count, f'{name} {hand}: missing key signature/cancellation {kind} ({len(found)}/{count})'
                    evidence.append({'frame': name, 'hand': hand, 'kind': kind, 'hits': found})
    return evidence


def verify_source_body(folder, data, report):
    """Canonical annotation-free ink repeats without changes to notes or rests."""
    written, duration, gap = repeat_expectations(data)
    frames = {frame['name']: frame for frame in report['frames']}
    reference = frames.get('baseline', frames['opening'])
    canonical = _load(folder, reference)
    repeated = _load(folder, frames['repeat'])
    first_x = canonical.width * PLAYHEAD - reference['clock'] * DENSITY
    next_x = repeated.width * PLAYHEAD + (duration + gap - frames['repeat']['clock']) * DENSITY
    # Include every visible source onset, including beat zero and source rests;
    # only measure-boundary strokes have independent practice geometry.
    width = min(round(duration * DENSITY), canonical.width - round(first_x) - 2,
                repeated.width - round(next_x) - 2)
    left_pad = 30
    before = notation_ink(canonical)[:, round(first_x) - left_pad:round(first_x) + width].copy()
    after = notation_ink(repeated)[:, round(next_x) - left_pad:round(next_x) + width].copy()
    staves = detect_staff_lines(canonical)
    # Identify actual full-grand-staff strokes in EACH crop from image columns.
    # A note stem cannot count: it does not cross the space between the staves.
    top = round(staves['right'].lines[0])
    bottom = round(staves['left'].lines[-1])
    for picture in (before, after):
        bars = np.flatnonzero(picture[top:bottom + 1].mean(axis=0) >= .97)
        for col in bars:
            before[:, max(0, col - 1):col + 2] = False
            after[:, max(0, col - 1):col + 2] = False
    contours = before.copy()
    for staff in staves.values():
        for rail in staff.lines:
            contours[round(rail) - 1:round(rail) + 2] = False
    assert contours.sum() >= 100, 'Canonical source baseline has no measurable musical ink'
    # Include ALL photographed canonical source ink, including source rests,
    # internal signatures and connectors. Blank trailing sustain space may
    # legitimately receive the following preparation's restoration header;
    # that derived header has its own authentic-glyph obligations above.
    last_source_column = int(np.flatnonzero(contours.any(axis=0))[-1]) + 3
    before, after = before[:, :last_source_column], after[:, :last_source_column]
    # Initial signatures occupy the pre-roll; the source crop starts 30px
    # before beat zero, while source-internal changes stay inside this crop.
    best = max(2 * np.count_nonzero(before[:, max(0, dx):min(before.shape[1], before.shape[1] + dx)] &
                                    after[:, max(0, -dx):min(after.shape[1], after.shape[1] - dx)]) /
               (before[:, max(0, dx):min(before.shape[1], before.shape[1] + dx)].sum() +
                after[:, max(0, -dx):min(after.shape[1], after.shape[1] - dx)].sum() + 1e-9)
               for dx in (-1, 0, 1))
    assert best >= .985, f'Repeated source body differs from canonical source ink ({best:.4f})'
    return {'dice': float(best), 'reference': reference['name'],
            'visible_beats': (before.shape[1] - left_pad) / DENSITY,
            'canonical_source_ink_pixels': int(contours.sum())}


def verify_repeat_pixels(folder, data, report):
    """Parent-facing verifier; failures raise AssertionError with pixel evidence."""
    _, duration, gap = repeat_expectations(data)
    expected = {'opening': -.5, 'rest-before': duration + gap / 2 - .125,
                'rest': duration + gap / 2, 'rest-after': duration + gap / 2 + .125,
                'repeat': duration + gap}
    frames = {frame['name']: frame for frame in report['frames']}
    assert expected.keys() <= frames.keys(), 'Missing required repeat framebuffer clocks'
    for name, clock in expected.items():
        assert abs(frames[name]['clock'] - clock) < 1e-7, f'{name}: incorrect capture clock'
    assert data['gap_beats'] == gap, 'Preparation duration must use upcoming full meter'
    result = {'rests': {}, 'boundaries': {}, 'gap_extra_ink': {}}
    for name in ('rest-before', 'rest', 'rest-after'):
        result['rests'][name] = verify_rest_frame(folder, data, frames[name])
        result['boundaries'][name] = verify_gap_boundaries(folder, data, frames[name])
        result['gap_extra_ink'][name] = verify_clean_gap(folder, data, frames[name], report)
    result['motion'] = verify_repeat_motion(folder, data, report)
    result['arrival'] = verify_next_source_arrival(folder, data, report)
    result['headers'] = verify_context_headers(folder, data, report)
    result['source_body'] = verify_source_body(folder, data, report)
    return result

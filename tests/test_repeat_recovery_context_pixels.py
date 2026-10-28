"""Real native recovery rests replace notation globally, across source passes.

Expected clocks are pinned below. Production assembles the score and semantic
preparation descriptor; only PNG rails and external font outlines prove ink.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw
import pytest

from continuous_repeat_pixel_helpers import DENSITY, PLAYHEAD, _glyph_hits, notation_ink
from piano_teacher.notation.reference_font import feature_glyphs
from piano_teacher.notation.pixel_proof import detect_staff_lines
from piano_teacher.notation.symbol_pixel_proof import _match_glyph
from piano_teacher.notation.pixel_ink import bright

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / 'tests/fixtures/continuous_repetition_context.musicxml'
# name, pass offset, retry target, preparation start/end, source D, stride
CASES = [('suppressed-context', 0., 6., 3., 6., 9., 12.),
         ('regular-gap-overlap', 10., 3., 9., 13., 7., 10.),
         ('previous-pass-overlap', 6., 1., 3., 7., 5., 6.)]


def _source_xml(name):
    tree = ET.fromstring(CONTEXT.read_text())
    if name == 'suppressed-context':
        for part in tree.findall('part'):
            second = part.findall('measure')[1]
            second.find('attributes/time/beats').text = '3'
            for note in second.findall('note'):
                note.find('duration').text = '12'
                if note.find('pitch') is not None:
                    note.find('type').text = 'half'
                    ET.SubElement(note, 'dot')
            third = deepcopy(second)
            third.set('number', '3')
            third.remove(third.find('attributes'))
            part.append(third)
    elif name == 'previous-pass-overlap':
        for part in tree.findall('part'):
            first, second = part.findall('measure')
            first.find('attributes/time/beats').text = '1'
            first.find('note/duration').text = '4'
            first.find('note/type').text = 'quarter'
            first.find('note').remove(first.find('note/dot'))
            for note in list(second.findall('note')):
                second.remove(note)
            # Actual source attacks at beats 1,2,3,4, on both staves. The
            # preceding pass's beats 3 and 4 must disappear in [3,7].
            for _ in range(4):
                note = ET.SubElement(second, 'note')
                pitch = ET.SubElement(note, 'pitch')
                ET.SubElement(pitch, 'step').text = 'C' if part.get('id') == 'RH' else 'G'
                ET.SubElement(pitch, 'octave').text = '3' if part.get('id') == 'RH' else '2'
                ET.SubElement(note, 'duration').text = '4'
                ET.SubElement(note, 'voice').text = '1'
                ET.SubElement(note, 'type').text = 'quarter'
    return ET.tostring(tree, encoding='unicode')


def build_recovery_fixture(case, folder):
    from piano_teacher.notation.practice_timeline import preparation_measure_descriptor
    from scripts.check_native_verovio_overlay import AuditCase
    from test_continuous_repeat_pixels import build_repeat_fixture

    name, offset, target, start, end, duration, stride = case
    source = folder / 'source.musicxml'
    source.write_text(_source_xml(name))
    data = build_repeat_fixture(AuditCase(name, str(source), 1,
                                         3 if name == 'suppressed-context' else 2, 'both'))
    assert data['model']['duration_beats'] == duration
    assert data['model']['practice_timeline']['stride_beats'] == stride
    context = next(measure for measure in reversed(data['model']['measures'])
                   if measure['start_beat'] <= target)
    preparation = preparation_measure_descriptor(context, start, data['model']['staff_order'])
    assert preparation['end_beat'] == end == offset + target
    data['state']['practice_preparation'] = {
        'pass_start_beat': offset, 'source_from_beat': target,
        'measure': preparation, 'phase': 'preparing'}
    data['state']['phase'] = 'preparing'
    data['state']['visual_offset_beats'] = offset
    data['recovery_expected'] = {'name': name, 'start': start, 'end': end}
    midpoint = (start + end) / 2
    data['repeat_frames'] = [
        {'name': tag, 'clock': midpoint + delta,
         'state': {'running': False, 'play_from_beat': target, 'count_in_beats': 0.}}
        for tag, delta in [('recovery-before', -.125), ('recovery', 0.), ('recovery-after', .125)]]
    return data


@pytest.fixture(scope='module', params=CASES, ids=[case[0] for case in CASES])
def recovery_capture(request, tmp_path_factory):
    retained = os.environ.get('REPEAT_RECOVERY_CAPTURE_ROOT')
    if retained:
        folder = Path(retained) / request.param[0]
        return folder, json.loads((folder / 'fixture.json').read_text()), json.loads((folder / 'repeat-report.json').read_text())
    from test_native_fingering import _godot, _run_godot
    folder = tmp_path_factory.mktemp('recovery-' + request.param[0])
    data = build_recovery_fixture(request.param, folder)
    payload = folder / 'fixture.json'
    payload.write_text(json.dumps(data))
    result = _run_godot([*_godot(), '--path', str(ROOT / 'godot'), '--rendering-method',
                         'gl_compatibility', '--audio-driver', 'Dummy', '--script',
                         str(ROOT / 'tests/godot/continuous_repeat_capture.gd'),
                         '--', str(payload), str(folder)], timeout=90)
    (folder / 'godot.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'SCRIPT ERROR' not in result.stdout + result.stderr
    return folder, data, json.loads((folder / 'repeat-report.json').read_text())


def _picture(folder, frame):
    with Image.open(folder / frame['base']) as raw:
        image = raw.convert('RGB')
    assert image.size == (1536, 520)
    return image


def _boundaries(image, expected, clock):
    staves = detect_staff_lines(image)
    ink = notation_ink(image)
    top, bottom = round(staves['right'].lines[0]), round(staves['left'].lines[-1])
    result = []
    for beat in (expected['start'], expected['end']):
        x = image.width * PLAYHEAD + (beat - clock) * DENSITY
        columns = [col for col in range(round(x - 2 * staves['right'].gap), round(x) + 2)
                   if ink[top:bottom + 1, col].mean() >= .97]
        assert columns and max(columns) - min(columns) <= 3, f'Missing or extra recovery boundary near beat {beat}: {columns}'
        result.append(float(np.mean(columns)))
    return staves, result


def _rest_box(staff, x):
    bounds = feature_glyphs()['rest_whole']['bounds']
    unit = staff.gap / 250
    left, top = round(x - bounds[2] * unit / 2) - 3, round(staff.lines[1] + bounds[1] * unit) - 3
    return left, top, left + round(bounds[2] * unit) + 6, top + round(bounds[3] * unit) + 6


def verify_recovery_pixels(folder, data, report, *, context_only=False):
    expected = data['recovery_expected']
    evidence = []
    for frame in report['frames']:
        image = _picture(folder, frame)
        staves, (left, right) = _boundaries(image, expected, frame['clock'])
        center = (left + right) / 2
        ink = notation_ink(image)
        for hand, staff in staves.items():
            score = _match_glyph(ink, feature_glyphs()['rest_whole'], staff.gap, center,
                                 staff.lines[1], centered=True, dxs=range(-2, 3), dys=range(-2, 3))
            assert score >= .80, f'{hand}: missing authentic centered recovery rest ({score:.3f})'
        if expected['name'] == 'suppressed-context':
            # The actually preceding audible context is G/+1, not the F/-2
            # measure suppressed at the preparation's own start beat 3.
            glyphs = feature_glyphs()
            for hand, staff in staves.items():
                def find(name, y):
                    half = glyphs[name]['bounds'][2] * staff.gap / 500
                    return _glyph_hits(bright(image), glyphs[name], staff,
                                       (left - 19 * staff.gap, left - half - 1), y)
                if hand == 'right':
                    hits = find('clef_f', staff.lines[1])
                    assert hits, 'Required recovery F clef missing before left boundary; suppressed context was treated as audible'
                for name, count in [('acc_natural', 1), ('acc_flat', 2)]:
                    hits = []
                    for y in np.arange(staff.lines[0] - staff.gap, staff.lines[-1] + staff.gap / 2, staff.gap / 2):
                        for hit in find(name, y):
                            if all(abs(hit['x'] - other['x']) > staff.gap / 2 for other in hits):
                                hits.append(hit)
                    assert len(hits) >= count, f'{hand}: required recovery {name} missing before left boundary ({len(hits)}/{count})'
        if not context_only:
            residual = ink.copy()
            for staff in staves.values():
                x0, y0, x1, y1 = _rest_box(staff, center)
                residual[y0:y1, x0:x1] = False
                for y in staff.lines:
                    residual[round(y) - 1:round(y) + 2] = False
            # Include the full height: an obsolete volta or its label is just
            # as much unexplained recovery ink as a notehead or extra rule.
            extra = int(residual[:, round(left) + 4:round(right) - 3].sum())
            assert extra <= 8, f'Extra boundary, source head or obsolete gap ink inside recovery silence ({extra} pixels)'
        evidence.append({'frame': frame['name'], 'boundaries': [left, right]})
    return evidence


def test_required_context_comes_from_last_audible_source(recovery_capture):
    verify_recovery_pixels(*recovery_capture, context_only=True)


def test_recovery_silence_globally_replaces_overlapping_pass_ink(recovery_capture):
    verify_recovery_pixels(*recovery_capture)


def _copy_capture(capture, folder):
    original, data, report = capture
    for frame in report['frames']:
        for key in ('file', 'base'):
            shutil.copy2(original / frame[key], folder / frame[key])
    return folder, data, report


def test_removed_actual_recovery_context_glyph_fails(recovery_capture, tmp_path):
    folder, data, report = recovery_capture
    if data['recovery_expected']['name'] != 'suppressed-context':
        pytest.skip('Case A is the explicit suppressed-context obligation')
    capture = _copy_capture(recovery_capture, tmp_path)
    verify_recovery_pixels(*capture)
    frame = next(frame for frame in report['frames'] if frame['name'] == 'recovery')
    image = _picture(tmp_path, frame)
    staves, (left, right) = _boundaries(image, data['recovery_expected'], frame['clock'])
    staff, glyph = staves['right'], feature_glyphs()['clef_f']
    bounds = glyph['bounds']
    unit = staff.gap / 250
    hits = _glyph_hits(bright(image), glyph, staff,
                       (left - 19 * staff.gap, left - bounds[2] * unit / 2 - 1), staff.lines[1])
    assert hits
    x0 = round(hits[0]['x'] - bounds[2] * unit / 2) - 3
    y0 = round(staff.lines[1] + bounds[1] * unit) - 3
    x1, y1 = x0 + round(bounds[2] * unit) + 6, y0 + round(bounds[3] * unit) + 6
    pixels = np.asarray(image).copy()
    # Erase the photographed clef, preserving measured staff colors per row.
    sample = round(left + 20)
    pixels[y0:y1, x0:x1] = pixels[y0:y1, sample:sample + 1]
    Image.fromarray(pixels).save(tmp_path / frame['base'])
    with pytest.raises(AssertionError, match='Required recovery F clef missing'):
        verify_recovery_pixels(*capture)


def test_inserted_grand_staff_rule_inside_recovery_silence_fails(recovery_capture, tmp_path):
    capture = _copy_capture(recovery_capture, tmp_path)
    folder, data, report = capture
    verify_recovery_pixels(*capture)
    frame = next(frame for frame in report['frames'] if frame['name'] == 'recovery')
    image = _picture(folder, frame)
    staves, (left, right) = _boundaries(image, data['recovery_expected'], frame['clock'])
    x = round((left + right) / 2 + staves['right'].gap * 2)
    top, bottom = round(staves['right'].lines[0]), round(staves['left'].lines[-1])
    color = image.getpixel((round(left), (top + bottom) // 2))
    ImageDraw.Draw(image).line((x, top, x, bottom), fill=color, width=2)
    image.save(folder / frame['base'])
    with pytest.raises(AssertionError, match='Extra boundary, source head or obsolete gap ink'):
        verify_recovery_pixels(*capture)

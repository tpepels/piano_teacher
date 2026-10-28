"""Bounded real-native framebuffer regressions for continuous repetition only."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageFilter
import pytest

from continuous_repeat_pixel_helpers import (
    PLAYHEAD, repeat_expectations, verify_repeat_pixels,
    verify_rest_frame, verify_gap_boundaries, verify_clean_gap, verify_repeat_motion,
    verify_context_headers, verify_source_body, verify_next_source_arrival,
)
from piano_teacher.notation.reference_font import feature_glyphs
from piano_teacher.notation.pixel_proof import detect_staff_lines
from piano_teacher.notation.pixel_ink import rasterize_outline

ROOT = Path(__file__).resolve().parents[1]
ALA = 'Ala_–_Joep_Beving.midi'
CASES = [('ala30', ALA, 30, 30, 'left'), ('ala32', ALA, 32, 32, 'both'),
         ('ala29-32', ALA, 29, 32, 'both'),
         ('source-rests', 'tests/fixtures/native_pixel_rest_probe.musicxml', 1, 4, 'right'),
         ('context', 'tests/fixtures/continuous_repetition_context.musicxml', 1, 2, 'both')]


def build_repeat_fixture(case, *, piece=None, plan=None, phrase=None):
    """Use real production engraving and one reusable whole-piece fingering plan."""
    from piano_teacher.fingering import project_model
    from scripts.check_native_verovio_overlay import fixture
    data, _ = fixture(case, piece=piece, phrase=phrase)
    data['hand'] = case.hand
    if plan is not None:
        data['model'] = project_model(data['model'], plan, source_musicxml=piece.source_musicxml)
    written, duration, gap = repeat_expectations(data)
    data['gap_beats'] = gap
    data['expected_source_duration_beats'] = duration
    data['expected_gap_beats'] = gap
    data['state'] = {'practice_timeline': data['model'].get('practice_timeline', {})}
    data['repeat_frames'] = [{'name': name, 'clock': clock} for name, clock in (
        ('opening', -.5), ('rest-before', duration + gap / 2 - .125),
        ('rest', duration + gap / 2), ('rest-after', duration + gap / 2 + .125),
        ('repeat', duration + gap))]
    data['repeat_frames'].insert(0, {'name': 'baseline', 'clock': -.5,
                                   'state': {'score_loop_enabled': False}})
    first_attack = min(float(event['beat']) for event in written.symbols
                       if event['kind'] == 'note' and not event.get('tie_stop')
                       and (case.hand == 'both' or event['staff'] == case.hand))
    if first_attack > 0:
        data['repeat_frames'].insert(-1, {'name': 'repeat-arrival',
                                         'clock': duration + gap + first_attack})
    # Genuine internal changes beyond the opening viewport still get explicit
    # native evidence; these fixture clocks do not derive from renderer state.
    if case.filename.endswith('continuous_repetition_context.musicxml'):
        data['repeat_frames'].insert(1, {'name': 'change-1', 'clock': float(written.bars[1]) - 1})
    return data


@pytest.fixture(scope='module')
def repeat_originals(tmp_path_factory):
    from piano_teacher.fingering import FingeringService
    from piano_teacher.importing.pieces import import_piece
    store = FingeringService(tmp_path_factory.mktemp('repeat-whole-piece-plans'))
    piece, _ = import_piece(ROOT / 'midi' / ALA)
    plan = store.prepare(piece, sha256((ROOT / 'midi' / ALA).read_bytes()).hexdigest())
    assert plan.status in ('ready', 'partial'), plan.error
    return piece, plan


@pytest.fixture(scope='module', params=CASES, ids=[case[0] for case in CASES])
def repeated_capture(request, repeat_capture_root):
    """Return (folder,data,report); optional retained captures avoid another Godot."""
    name, filename, first, last, hand = request.param
    retained = os.environ.get('CONTINUOUS_REPEAT_CAPTURE_ROOT')
    if retained:
        folder = Path(retained) / (os.environ.get('CONTINUOUS_REPEAT_CAPTURE_PREFIX', '') + name)
        return (folder, json.loads((folder / 'fixture.json').read_text()),
                json.loads((folder / 'repeat-report.json').read_text()))
    from scripts.check_native_verovio_overlay import AuditCase
    from test_native_fingering import _godot, _run_godot
    piece, plan = request.getfixturevalue('repeat_originals') if filename == ALA else (None, None)
    data = build_repeat_fixture(AuditCase(name, filename, first, last, hand), piece=piece, plan=plan)
    folder = repeat_capture_root / name
    folder.mkdir()
    payload = folder / 'fixture.json'
    payload.write_text(json.dumps(data))
    (folder / 'score.musicxml').write_text(data['xml'])
    result = _run_godot([*_godot(), '--path', str(ROOT / 'godot'),
        '--rendering-method', 'gl_compatibility', '--audio-driver', 'Dummy',
        '--script', str(ROOT / 'tests/godot/continuous_repeat_capture.gd'),
        '--', str(payload), str(folder)], timeout=90)
    (folder / 'godot.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'SCRIPT ERROR' not in result.stdout + result.stderr
    return folder, data, json.loads((folder / 'repeat-report.json').read_text())


@pytest.fixture(scope='module')
def repeat_capture_root(tmp_path_factory):
    return tmp_path_factory.mktemp('continuous-repeat-captures')


def test_each_staff_has_authentic_centered_preparation_rest(repeated_capture):
    folder, data, report = repeated_capture
    for frame in report['frames']:
        if frame['name'] in ('rest-before', 'rest', 'rest-after'):
            verify_rest_frame(folder, data, frame)


def test_continuous_repeat_framebuffers(repeated_capture):
    verify_repeat_pixels(*repeated_capture)


def test_rest_boundaries_span_grand_staff_and_clear_incoming_onset(repeated_capture):
    folder, data, report = repeated_capture
    for frame in report['frames']:
        if frame['name'] in ('rest-before', 'rest', 'rest-after'):
            verify_gap_boundaries(folder, data, frame)


def test_no_extra_clef_key_or_meter_inside_the_preparation_measure(repeated_capture):
    folder, data, report = repeated_capture
    for frame in report['frames']:
        if frame['name'] in ('rest-before', 'rest', 'rest-after'):
            verify_clean_gap(folder, data, frame, report)


def test_equal_eighthbeat_clock_steps_move_twelve_actual_pixels(repeated_capture):
    verify_repeat_motion(*repeated_capture)


def test_upcoming_source_head_arrives_at_playhead_after_full_nominal_meter(repeated_capture):
    verify_next_source_arrival(*repeated_capture)


def test_opening_internal_and_gap_start_context_are_engraved(repeated_capture):
    verify_context_headers(*repeated_capture)


def test_source_notes_rests_and_internal_ink_repeat_unchanged(repeated_capture):
    verify_source_body(*repeated_capture)


def test_fingering_digits_remain_annotation_only_and_source_bound(repeated_capture):
    from test_native_fingering import _verify_numbers
    folder, data, report = repeated_capture
    assignments = {event['id']: event['fingering']
                   for event in data['model']['notation_events'] if 'fingering' in event}
    for frame in report['frames']:
        if assignments:
            assert frame['labels'], 'Real whole-piece fingering plan needs visible annotations'
        if data['hand'] == 'both':
            _verify_numbers(folder, frame, len(frame['labels']))
        else:
            _verify_dim_numbers(folder, frame)
        for label in frame['labels']:
            for event_id in label['event_ids']:
                assert assignments[event_id]['finger'] == label['finger']
                assert assignments[event_id]['hand'] == label['hand']


def _verify_dim_numbers(folder, frame):
    """The existing digit oracle's identical shape gates, using pixel contrast.

    Its absolute RGB>100 mask cannot see a dim hand or its dim public-font
    reference. Subtract the photographed backgrounds, keeping BOTH hands,
    the .80 IoU gate, .12 family margin and canonical-ink clearance checks.
    """
    base = np.asarray(Image.open(folder / frame['base']).convert('RGB')).astype(int)
    numbered = np.asarray(Image.open(folder / frame['file']).convert('RGB')).astype(int)
    delta = np.max(abs(numbered - base), axis=2)
    claimed = np.zeros(delta.shape, dtype=bool)
    source_contrast = np.max(abs(base - base[0, -1]), axis=2)
    for label in frame['labels']:
        x, y, width, height = label['rect']
        x0, y0, x1, y1 = int(x), int(y), int(np.ceil(x + width)), int(np.ceil(y + height))
        assert 30 <= x0 < x1 < base.shape[1] and 0 < y0 < y1 < base.shape[0]
        cell = delta[y0:y1, x0:x1]
        observed = cell > max(12, float(cell.max()) * .4)
        assert observed.sum() > 12, 'Missing fingering ink in the actual framebuffer'
        reference = np.asarray(Image.open(folder / label['reference']).convert('RGB')).astype(int)
        contrast = np.max(abs(reference - reference[0, 0]), axis=2)
        reference_mask = contrast > float(contrast.max()) * .4
        cell_width = reference.shape[1] // 5
        candidates = [reference_mask[:, i * cell_width:(i + 1) * cell_width] for i in range(5)]
        assert all(candidate.shape == observed.shape for candidate in candidates)
        scores = [float((observed & candidate).sum() / max(1, (observed | candidate).sum()))
                  for candidate in candidates]
        finger = label['finger'] - 1
        assert int(np.argmax(scores)) == finger, (label, scores)
        assert scores[finger] > .80, (label, scores)
        assert scores[finger] - max(score for i, score in enumerate(scores) if i != finger) > .12
        expected_ink = np.zeros(delta.shape, dtype=np.uint8)
        expected_ink[y0:y1, x0:x1] = candidates[finger] * 255
        clearance = np.asarray(Image.fromarray(expected_ink).filter(ImageFilter.MaxFilter(5))) > 0
        assert not (clearance & (source_contrast > float(contrast.max()) * .8)).any(), label
        claimed[y0:y1, x0:x1] = True
    assert not ((delta > 12) & ~claimed).any(), 'Unexpected extra annotation ink'


def test_actual_notehead_clicks_in_two_passes_target_original_source(repeated_capture):
    folder, data, report = repeated_capture
    if (data['first_bar'], data['last_bar']) not in ((30, 30), (32, 32)):
        return  # These short Ala passages guarantee two visible annotated copies.
    clicks = report['clicks']
    assert len(clicks) == 2 and all(item['opened'] for item in clicks), clicks
    assert len({item['pass_index'] for item in clicks}) == 2, clicks
    sources = {item['expected_source_id'] for item in clicks}
    assert len(sources) == 1, clicks
    source = sources.pop()
    canonical_sources = {event['source_id'] for event in data['model']['notation_events']
                         if event['kind'] == 'note'}
    assert source in canonical_sources
    assert report['interactions'] == [{'source_id': source, 'finger': 5}] * 2
    frame = next(frame for frame in report['frames'] if frame['name'] == 'repeat')
    instances = [item for item in frame['instances'] if item['source_id'] == source]
    assert {item['pass_index'] for item in clicks} <= {item['pass_index'] for item in instances}


def _copy_capture(capture, tmp_path):
    folder, data, report = capture
    for frame in report['frames']:
        for key in ('file', 'base'):
            shutil.copy2(folder / frame[key], tmp_path / frame[key])
    return tmp_path, data, report


def _rest_image(capture):
    folder, data, report = capture
    frame = next(frame for frame in report['frames'] if frame['name'] == 'rest')
    path = folder / frame['base']
    with Image.open(path) as raw:
        image = raw.convert('RGB')
    return path, image, frame


def _erase_keep_rails(image, box, sample_x):
    """Erase actual ink while preserving measured horizontal staff pixels."""
    pixels = np.asarray(image).copy()
    x0, y0, x1, y1 = box
    pixels[y0:y1, x0:x1] = pixels[y0:y1, sample_x:sample_x + 1]
    return Image.fromarray(pixels)


def _rest_box(image, staff, x):
    bounds = feature_glyphs()['rest_whole']['bounds']
    unit = staff.gap / 250
    left = round(x - bounds[2] * unit / 2) - 3
    top = round(staff.lines[1] + bounds[1] * unit) - 3
    return left, top, left + round(bounds[2] * unit) + 6, top + round(bounds[3] * unit) + 6


@pytest.mark.parametrize('hand', ['right', 'left'])
def test_deleted_actual_rest_fails_including_inactive_staff(repeated_capture, tmp_path, hand):
    capture = _copy_capture(repeated_capture, tmp_path)
    folder, data, report = capture
    path, image, frame = _rest_image(capture)
    observed = verify_rest_frame(folder, data, frame)
    staff = detect_staff_lines(image)[hand]
    x = observed[hand]['x']
    _erase_keep_rails(image, _rest_box(image, staff, x), round(x - 3 * staff.gap)).save(path)
    with pytest.raises(AssertionError, match='missing authentic centered'):
        verify_repeat_pixels(*capture)


def test_inserted_authentic_clef_inside_gap_fails(repeated_capture, tmp_path):
    capture = _copy_capture(repeated_capture, tmp_path)
    folder, data, report = capture
    path, image, frame = _rest_image(capture)
    verify_clean_gap(folder, data, frame, report)
    staff = detect_staff_lines(image)['right']
    glyph = feature_glyphs()['clef_g']
    bounds = glyph['bounds']
    unit = staff.gap / 250
    mask = rasterize_outline(glyph['svg'], round(bounds[2] * unit), round(bounds[3] * unit))
    left = round(image.width * PLAYHEAD + 2.5 * staff.gap - mask.shape[1] / 2)
    top = round(staff.lines[-2] + bounds[1] * unit)
    pixels = np.asarray(image).copy()
    pixels[top:top + mask.shape[0], left:left + mask.shape[1]][mask] = (234, 244, 237)
    Image.fromarray(pixels).save(path)
    with pytest.raises(AssertionError, match='unexpected clef/key/time'):
        verify_repeat_pixels(*capture)


def test_removed_grand_staff_boundary_fails(repeated_capture, tmp_path):
    capture = _copy_capture(repeated_capture, tmp_path)
    folder, data, report = capture
    path, image, frame = _rest_image(capture)
    left = round(verify_gap_boundaries(folder, data, frame)[0])
    _erase_keep_rails(image, (left - 4, 0, left + 5, image.height), left + 12).save(path)
    with pytest.raises(AssertionError, match='boundary missing or detached'):
        verify_repeat_pixels(*capture)


def test_shifted_incoming_pass_fails_even_with_unchanged_report(repeated_capture, tmp_path):
    capture = _copy_capture(repeated_capture, tmp_path)
    folder, data, report = capture
    verify_source_body(*capture)
    frame = next(frame for frame in report['frames'] if frame['name'] == 'repeat')
    path = folder / frame['base']
    with Image.open(path) as raw:
        image = raw.convert('RGB')
    x = round(image.width * PLAYHEAD) - 30
    tile = image.crop((x, 0, image.width - 24, image.height))
    changed = _erase_keep_rails(image, (x, 0, image.width, image.height), x - 24)
    changed.paste(tile, (x + 24, 0))
    changed.save(path)
    with pytest.raises(AssertionError, match='Repeated source body differs|source head misses'):
        verify_repeat_pixels(*capture)


def test_changed_visible_pause_duration_fails_with_original_clocks(repeated_capture, tmp_path):
    capture = _copy_capture(repeated_capture, tmp_path)
    folder, data, report = capture
    path, image, frame = _rest_image(capture)
    verify_rest_frame(folder, data, frame)
    boundaries = verify_gap_boundaries(folder, data, frame)
    center = sum(boundaries) / 2
    boundary = round(boundaries[1])
    # Add one quarter-note beat of silence to the PNG: move the incoming
    # pass AND end boundary by 96px, and recenter the two rests by 48px.
    tile = image.crop((boundary - 30, 0, image.width - 96, image.height))
    changed = _erase_keep_rails(image, (boundary - 30, 0, image.width, image.height), boundary - 40)
    changed.paste(tile, (boundary - 30 + 96, 0))
    for staff in detect_staff_lines(image).values():
        box = _rest_box(image, staff, center)
        rest = image.crop(box)
        changed = _erase_keep_rails(changed, box, round(center - 3 * staff.gap))
        changed.paste(rest, (box[0] + 48, box[1]))
    changed.save(path)
    with pytest.raises(AssertionError, match='missing authentic centered|boundary missing'):
        verify_repeat_pixels(*capture)

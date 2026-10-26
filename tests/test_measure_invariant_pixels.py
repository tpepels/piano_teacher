"""One musical scale, measured from actual production app framebuffers."""
from __future__ import annotations

from collections import defaultdict
import json
import os
from pathlib import Path
import shutil

from PIL import Image
import pytest

from measure_invariant_fixtures import CASES, DENSITY, ROOT, prepare_measure_fixture
from piano_teacher.notation.measure_pixels import verify_measure_frame
from piano_teacher.notation.proof import read_written_score


def boundary_inventory(data, gap, copies=6):
    """Quarter-beat boundaries from independently read original MusicXML.

    Focused sources have regular full-grand-staff rules. Double/repeat stroke
    typography has separate verifier controls; it cannot create extra beats.
    The first source opening has no printed rule; preparation owns each later
    source-copy junction exactly once.
    """
    written = read_written_score(data['xml'])
    bars = list(map(float, written.bars))
    assert [(m['start_beat'], m['end_beat']) for m in data['model']['measures']] == list(zip(bars, bars[1:]))
    assert all(b > a for a, b in zip(bars, bars[1:]))
    duration, stride = bars[-1], bars[-1] + gap
    boundaries = {}
    for copy in range(copies):
        for beat in bars[1:]:
            boundaries[copy*stride + beat] = {'beat': copy*stride + beat}
        boundaries[(copy+1)*stride] = {'beat': (copy+1)*stride}
    return list(boundaries.values())


def _capture(folder):
    from test_native_fingering import _godot, _run_godot
    result = _run_godot([*_godot(), '--path', str(ROOT/'godot'),
        '--rendering-method', 'gl_compatibility', '--audio-driver', 'Dummy',
        '--script', str(ROOT/'tests/godot/measure_invariant_capture.gd'), '--',
        str(folder), str(folder/'capture.json')], timeout=120)
    output = result.stdout + result.stderr
    (folder/'godot.log').write_text(output)
    assert result.returncode == 0 and 'SCRIPT ERROR' not in output and 'ERROR:' not in output, output
    return json.loads((folder/'measure-frames.json').read_text())


@pytest.fixture(scope='module', params=list(CASES))
def measure_capture(request, tmp_path_factory):
    retained = os.environ.get('MEASURE_INVARIANT_CAPTURE_ROOT')
    folder = Path(retained)/request.param if retained else tmp_path_factory.mktemp('measure-'+request.param)
    if retained:
        data = json.loads((folder/'fixture.json').read_text())
        configuration = json.loads((folder/'capture.json').read_text())
        report = json.loads((folder/'measure-frames.json').read_text())
    else:
        data, configuration = prepare_measure_fixture(request.param, folder)
        report = _capture(folder)
    return folder, data, configuration, report


def measure_capture_evidence(capture):
    folder, data, configuration, report = capture
    boundaries = boundary_inventory(data, configuration['gap_beats'])
    calibrations, evidence = {}, []
    for frame in report['frames']:
        key = tuple(frame['viewport'])
        expected = boundaries if frame.get('loop_enabled',True) else [
            boundary for boundary in boundaries if boundary['beat'] <= data['model']['duration_beats']]
        with Image.open(folder/frame['file']) as raw:
            result = verify_measure_frame(raw.convert('RGB'), expected,
                clock_beat=frame['clock'], density=DENSITY*frame['pixel_scale'],
                clearance_px=calibrations.get(key), pixel_scale=frame['pixel_scale'])
        assert result['passed'], (frame['name'], result['errors'])
        calibrations.setdefault(key, result['clearance_px'])
        evidence.append({**frame, 'proof': result})
    return evidence


@pytest.fixture(scope='module')
def measured_frames(measure_capture):
    return measure_capture, measure_capture_evidence(measure_capture)


def test_equal_duration_measures_have_equal_actual_pixel_widths(measured_frames):
    (folder, data, _, _), evidence = measured_frames
    (folder/'measure-width-evidence.json').write_text(json.dumps(evidence, indent=2))
    widths = [width for frame in evidence for width in frame['proof']['widths']]
    assert widths
    for frame in evidence:
        assert frame['model_loads'] == 1, 'Tempo changes must not reload/re-engrave the exercise'
        assert all(abs(w['observed_px']-w['duration_beats']*DENSITY*frame['pixel_scale']) <= 1.5
                   for w in frame['proof']['widths'])
    if read_written_score(data['xml']).bars[1] == .5:
        assert any(w['duration_beats'] == .5 and abs(w['observed_px']-48*f['pixel_scale']) <= 1.5
                   for f in evidence for w in f['proof']['widths'])
        assert any(w['duration_beats'] == 4 and abs(w['observed_px']-384*f['pixel_scale']) <= 1.5
                   for f in evidence for w in f['proof']['widths'])


def test_multiple_photographed_boundaries_move_at_bpm_velocity(measured_frames):
    (folder, _, _, _), evidence = measured_frames
    groups = defaultdict(list)
    for frame in evidence:
        if frame['group'] == 'pause-resume':
            continue
        groups[tuple(frame['viewport']), frame['bpm'], frame['group']].append(frame)
    measurements = []
    for frames in groups.values():
        frames.sort(key=lambda f: f['index'])
        for before, after in zip(frames, frames[1:]):
            left = {r['beat']: r['observed_x'] for r in before['proof']['boundaries']}
            right = {r['beat']: r['observed_x'] for r in after['proof']['boundaries']}
            common = sorted(left.keys() & right.keys())
            assert len(common) >= 2, 'Motion needs multiple independently photographed features'
            seconds = after['seconds'] - before['seconds']
            expected = DENSITY * before['pixel_scale'] * before['bpm'] / 60 * seconds
            steps = [left[b]-right[b] for b in common]
            assert all(abs(step-expected) <= 1.5 for step in steps), (before['name'], steps, expected)
            measurements.append({'from':before['name'], 'to':after['name'], 'seconds':seconds,
                'bpm':before['bpm'], 'expected_displacement_px':expected,
                'observed_displacements_px':steps, 'observed_velocities_px_per_second':[s/seconds for s in steps]})
    # Longer transitions constrain accumulated drift too. The calibration is
    # never restarted at a gap or repetition, even when a short raster step
    # alternates between half-pixel stroke centroids.
    for viewport,bpm in sorted({(tuple(frame['viewport']),frame['bpm']) for frame in evidence}):
        windows = [groups[viewport,bpm,name] for name in ('populated','into-rest','rest','repeat')]
        for previous,following in zip(windows,windows[1:]):
            before,after = previous[-1],following[0]
            left = {row['beat']:row['observed_x'] for row in before['proof']['boundaries']}
            right = {row['beat']:row['observed_x'] for row in after['proof']['boundaries']}
            common = sorted(left.keys() & right.keys())
            if len(common)<2 and viewport[0]<1000:
                continue # The compact viewport cannot keep two widely separated rules in view.
            assert len(common)>=2
            seconds = (after['clock']-before['clock'])*60/bpm
            expected = DENSITY*before['pixel_scale']*(after['clock']-before['clock'])
            steps = [left[beat]-right[beat] for beat in common]
            assert all(abs(step-expected)<=1.5 for step in steps),(before['name'],after['name'],steps,expected)
            measurements.append({'from':before['name'],'to':after['name'],'seconds':seconds,
                'bpm':bpm,'expected_displacement_px':expected,'observed_displacements_px':steps,
                'observed_velocities_px_per_second':[step/seconds for step in steps]})
    (folder/'measure-motion-evidence.json').write_text(json.dumps(measurements, indent=2))


def test_pause_and_resume_keep_exact_pixels_without_reengraving(measured_frames):
    import numpy as np
    (folder, _, _, _), evidence = measured_frames
    groups = defaultdict(list)
    for frame in evidence:
        if frame['group'] == 'pause-resume':
            groups[tuple(frame['viewport']),frame['bpm']].append(frame)
    assert len(groups) == 9
    for frames in groups.values():
        frames.sort(key=lambda frame: frame['index'])
        baseline = np.asarray(Image.open(folder/frames[0]['file']))
        for frozen in frames[1:4]:
            assert np.array_equal(baseline,np.asarray(Image.open(folder/frozen['file']))),frozen['name']
        assert not np.array_equal(baseline,np.asarray(Image.open(folder/frames[4]['file'])))


def test_independent_repeat_meter_preserves_pickup_but_prepares_a_full_measure(measure_capture):
    from continuous_repeat_pixel_helpers import repeat_expectations
    _, data, configuration, _ = measure_capture
    written, duration, gap = repeat_expectations(data)
    assert duration == written.bars[-1]
    assert gap == configuration['gap_beats']


CORRUPTIONS = ['compressed-rest', 'moved-boundary', 'duplicate-boundary', 'local-density',
               'changed-speed', 'translated-rest', 'repeat-jump']


def _source_head_is_present(folder, data, frame):
    from continuous_repeat_pixel_helpers import _context, notation_ink
    from piano_teacher.notation.feature_pixels import _feature_glyphs
    from piano_teacher.notation.pixel_proof import detect_staff_lines, expected_y
    from piano_teacher.notation.symbol_pixel_proof import _match_glyph
    written = read_written_score(data['xml'])
    event = next(event for event in written.symbols if event['kind'] == 'note'
                 and event['staff'] == 'left' and float(event['beat']) == frame['clock']
                 and not event.get('chord') and not event.get('tie_stop'))
    image = Image.open(folder/frame['file']).convert('RGB')
    staff = detect_staff_lines(image)['left']
    measure = max(i for i, beat in enumerate(written.bars[:-1]) if beat <= frame['clock'])
    y = expected_y(staff,tuple(event['spelling']),_context(written,measure,'left')[2])
    glyph = 'head_'+(event['note_type'] if event['note_type'] in ('half','whole') else 'black')
    score = _match_glyph(notation_ink(image),_feature_glyphs()[glyph],staff.gap,image.width*.42,y,
                         centered=True,dxs=range(-2,3),dys=range(-2,3))
    assert score >= .79, ('The independent source-head/timing control failed',score)


@pytest.fixture(scope='module')
def corruption_reference(tmp_path_factory):
    folder = tmp_path_factory.mktemp('measure-corruption-reference')
    data, configuration = prepare_measure_fixture('source-rests', folder)
    configuration.update(viewports=[(1220,780)], tempos=[80])
    configuration['samples'] = [sample for sample in configuration['samples'] if sample['name'] != 'pause-resume']
    (folder/'capture.json').write_text(json.dumps(configuration))
    good = _capture(folder)
    boundaries = boundary_inventory(data, configuration['gap_beats'])
    first = good['frames'][0]
    reference = verify_measure_frame(Image.open(folder/first['file']), boundaries,
                                    clock_beat=first['clock'], density=DENSITY)
    assert reference['passed'], reference['errors']
    _source_head_is_present(folder,data,first)
    return folder, data, configuration, reference


def _corruption_frame_proofs(folder, data, configuration, reference):
    boundaries = boundary_inventory(data, configuration['gap_beats'])
    report = json.loads((folder/'measure-frames.json').read_text())
    for frame in report['frames']:
        expected = boundaries if frame.get('loop_enabled', True) else [
            boundary for boundary in boundaries
            if boundary['beat'] <= data['model']['duration_beats']]
        yield frame, verify_measure_frame(Image.open(folder/frame['file']), expected,
            clock_beat=frame['clock'], density=DENSITY,
            clearance_px=reference['clearance_px'])


def test_uncorrupted_whole_sequence_passes_the_corruption_verifier(corruption_reference):
    folder, data, configuration, reference = corruption_reference
    for frame, proof in _corruption_frame_proofs(folder, data, configuration, reference):
        assert proof['passed'], (frame['name'], proof['errors'])


@pytest.mark.parametrize('corruption', CORRUPTIONS)
def test_render_corruptions_fail_independent_measure_or_motion_proof(tmp_path, corruption, corruption_reference):
    original, data, original_configuration, reference = corruption_reference
    folder = tmp_path
    configuration = json.loads(json.dumps(original_configuration))
    for name in ('native.json','fixture.json','score.musicxml'):
        shutil.copy2(original/name,folder/name)
    # Keep the real, correct input frame. Corruption changes GDScript paint or
    # projection only, never PNG pixels, notes, BPM or source model bytes.
    before_model = (folder/'native.json').read_bytes()
    configuration['corruption'] = corruption
    (folder/'capture.json').write_text(json.dumps(configuration))
    report = _capture(folder)
    _source_head_is_present(folder,data,report['frames'][0])
    failures = []
    for frame, proof in _corruption_frame_proofs(folder, data, configuration, reference):
        failures.extend(f"{frame['name']}: {error}" for error in proof['errors'])
    assert (folder/'native.json').read_bytes() == before_model
    assert {f['bpm'] for f in report['frames']} == {80}
    assert failures, f'Unnoticed {corruption} renderer corruption'
    (folder/'corruption-evidence.json').write_text(json.dumps({'corruption':corruption,'rejected':True,'errors':failures},indent=2))

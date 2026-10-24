"""The full-inventory capture grid preserves exact source clock witnesses."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def godot_run(script, args=(), timeout=30, graphical=False):
    binary = shutil.which('godot') or shutil.which('godot4')
    if not binary:
        pytest.skip('Godot is required for the capture protocol')
    flags = ['--headless'] if not graphical else [
        '--rendering-method', 'gl_compatibility', '--resolution', '16x16',
        '--position', '-16384,-16384', '--disable-vsync', '--max-fps', '0']
    return subprocess.run([binary, *flags, '--audio-driver', 'Dummy', '--path',
        str(ROOT/'godot'), '--script', str(script), '--', *map(str, args)],
        capture_output=True, text=True, timeout=timeout,
        env={**os.environ, 'LIBGL_ALWAYS_SOFTWARE': '1'})


def test_uniform_grid_is_opt_in_bounded_and_preserves_source_f5_collisions(tmp_path):
    script = tmp_path/'schedule.gd'
    script.write_text('''extends SceneTree
func _initialize():
    var harness = load("%s").new()
    if not harness.has_method("_capture_schedule"):
        push_error("Full-inventory capture scheduler is missing")
        quit(1)
        return
    var original = [0.0, 0.33333333, 0.9375, 1.0]
    var data = {"sample_beats":original,"model":{"duration_beats":1.0}}
    var focused = harness._capture_schedule(data, 28800.0)
    assert(focused["samples"] == original)
    data["full_symbol_inventory"] = true
    var full = harness._capture_schedule(data, 28800.0)
    assert(full["samples"].has(0.33333333))
    var names = {}
    var previous = 0.0
    for clock in full["samples"]:
        var name = "native-%%.5f.png" %% clock
        assert(not names.has(name), "Grid overwrites original source onset")
        names[name] = true
        assert(clock-previous <= 0.15+0.00001)
        assert((clock-previous)*28800.0 <= 96.0+0.01)
        previous = clock
    assert(full["samples"][0] == 0.0)
    assert(full["samples"][-1] == 1.0)
    assert(full["added"] > 200)
    var ordinary = harness._capture_schedule(data, 1.0)
    assert(ordinary["interval"] <= 0.15)
    print("EXTRA_CAPTURE_SCHEDULE_OK")
    harness.free()
    quit()
''' % str(ROOT/'tests/godot/native_verovio_overlay.gd'))
    result = godot_run(script)
    assert result.returncode == 0, result.stdout+result.stderr
    assert 'EXTRA_CAPTURE_SCHEDULE_OK' in result.stdout


@pytest.mark.skipif(not os.environ.get('DISPLAY'), reason='Actual PNG requires a display')
def test_grid_frames_are_normal_precise_and_rest_controls_only_at_source_onsets(tmp_path):
    from scripts.check_native_verovio_overlay import AuditCase, fixture
    data, _ = fixture(AuditCase('extra-grid',
        'tests/fixtures/native_pixel_rest_probe.musicxml', 1, 1))
    data.pop('xml')
    data.update(phase3_full=True, full_symbol_inventory=True, sample_beats=[0., 2.])
    path = tmp_path/'fixture.json'
    path.write_text(json.dumps(data))
    run = godot_run(ROOT/'tests/godot/native_verovio_overlay.gd', [path, tmp_path],
                    timeout=90, graphical=True)
    assert run.returncode == 0, run.stdout+run.stderr
    report = json.loads((tmp_path/'native-overlay-report.json').read_text())
    clocks = [r['clock'] for r in report['frames']]
    assert clocks[0] == 0 and clocks[-1] == data['model']['duration_beats']
    assert max(b-a for a, b in zip(clocks, clocks[1:])) <= .15001
    assert len(clocks) > 20
    assert len(set(r['file'] for r in report['frames'])) == len(clocks)
    assert all((tmp_path/r['file']).is_file() for r in report['frames'])
    assert {r['clock'] for r in report['rest_difference_controls']} == {0., 2.}
    schedule = report['extra_symbol_schedule']
    assert schedule['added'] == len(clocks)-2
    assert schedule['geometry_is_proof'] is False

"""Exercise the ordinary launcher and real desktop pixels without MIDI input."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_visible_playback_rejects_native_fallback_warning():
    from scripts.check_visible_playback import require_clean_log
    with pytest.raises(RuntimeError,match="Native notation fallback"):
        require_clean_log("VISIBLE_RESULT:PASS samples=44\nWARNING: Native notation fallback: missing atlas")


@pytest.mark.parametrize("play_from", [0.0, 1.0])
def test_native_sampling_tracks_one_occurrence_when_next_repeat_is_visible(tmp_path, play_from):
    """A repeated source ID must not make the measured attack jump a passage."""
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot unavailable")
    from test_score_motion_render import make_render_fixture

    make_render_fixture(tmp_path)
    probe = tmp_path / "sample_occurrence.gd"
    probe.write_text(f'''extends "{ROOT / 'tests/godot/live_playback.gd'}"
class FixtureApp extends "{ROOT / 'tests/godot/native_production_fixture.gd'}":
    func _transport_beat_now() -> float:
        return float(last_state.get("clock_beat", 0.0))
func _initialize() -> void:
    call_deferred("probe")
func probe() -> void:
    root.size = Vector2i(1600, 1000)
    app = FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    var error: String = app.load_native_fixture("{tmp_path}")
    if not error.is_empty():
        push_error(error)
        quit(1)
        return
    var view = app.practice_view.stage.renderer
    var note: Dictionary = app.score_layout.notes[0]
    var later_pass_seen := false
    for beat in [-.1, 1.1]:
        app.last_state.merge({{"running":true, "paused":false,
            "phase":"playing", "clock_beat":beat, "transport_id":19,
            "play_from_beat":{play_from}, "score_loop_enabled":true,
            "visual_offset_beats":0.0}}, true)
        app._process(0.0)
        await process_frame
        await process_frame
        # This width includes the next source pass during the second sample.
        view.size = Vector2(1322, 473)
        view.queue_redraw()
        await process_frame
        RenderingServer.force_draw()
        var point: Vector2 = note_position(note)
        for instance in view.drawn_note_instances:
            if str(instance.event_id) == str(note.id) and int(instance.pass_index)>0:
                var painted: Vector2 = instance.position
                later_pass_seen = later_pass_seen or painted.x > view.size.x * .9
        print("OCCURRENCE_SAMPLE:", JSON.stringify({{"beat":beat,
            "x":point.x,"density":view.timeline.pixels_per_beat,
            "beam":(view.get_global_transform_with_canvas() * Vector2(view.size.x*.42, 0)).x}}))
    print("NEXT_SOURCE_PASS_VISIBLE:", later_pass_seen)
    quit(0)
''')
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"), "--script", str(probe)],
        capture_output=True, text=True, timeout=45,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "NEXT_SOURCE_PASS_VISIBLE:true" in output, output
    samples = [json.loads(line.split(":", 1)[1]) for line in output.splitlines()
               if line.startswith("OCCURRENCE_SAMPLE:")]
    assert len(samples) == 2, output
    assert samples[0]["x"] - samples[1]["x"] == pytest.approx(
        1.2 * samples[0]["density"], abs=.02), output

    for sample in samples:
        assert sample["x"] + (sample["beat"] + play_from) * sample["density"] == pytest.approx(
            sample["beam"], abs=.02), output


def test_launcher_moves_visible_notes_at_four_tempos(tmp_path):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Visible playback requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_visible_playback.py"),
         "--output-dir", str(tmp_path)], cwd=ROOT,
        env={**os.environ,"PIANO_TEACHER_NATIVE_NOTATION":"1"},
        capture_output=True, text=True, timeout=240,
    )
    assert result.returncode == 0, result.stdout + result.stderr + (
        (tmp_path / "godot.log").read_text(errors="replace")
        if (tmp_path / "godot.log").exists() else "")
    assert "VISIBLE_RESULT:PASS samples=44" in result.stdout
    report=json.loads((tmp_path/"samples.json").read_text())
    assert report["failures"]==[]
    assert all(sample["native_ready"] and sample["native_visible"]
               for sample in report["samples"])

"""Unchanged backend polls must let the actual Godot framebuffer sleep."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def test_idle_polls_sleep_but_changed_feedback_and_playback_still_render(tmp_path):
    from piano_teacher.server import PracticeEngine
    from test_native_fingering import _godot, _run_godot

    midi = tmp_path / "chords.mid"
    shutil.copyfile(ROOT / "tests/fixtures/musical_fidelity/midi_four_four.mid", midi)
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    try:
        engine.load(str(midi))
        payload = {"model": engine.semantic_score(),
                   "layout": engine.geometry(), "state": engine.state()}
    finally:
        engine.db.close()
    (tmp_path / "native.json").write_text(json.dumps(payload))
    result = _run_godot([*_godot(), "--path", str(ROOT / "godot"),
        "--audio-driver", "Dummy", "--rendering-method", "gl_compatibility",
        "--script", str(ROOT / "tests/godot/idle_rendering.gd"), "--", str(tmp_path),
        str(ROOT / "tests/godot/native_production_fixture.gd")],
        timeout=45)
    output = result.stdout + result.stderr
    (tmp_path / "godot.log").write_text(output)
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "ERROR:" not in output, output
    assert "IDLE_RENDERING_FAILURES:0" in output, output

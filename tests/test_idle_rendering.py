"""Unchanged polls must reuse retained source ink while the blank world moves."""
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def test_identical_polls_reuse_retained_ink_while_world_and_playback_move(tmp_path):
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
        timeout=45, env={**os.environ,"HOME":str(tmp_path/"home"),
            "XDG_DATA_HOME":str(tmp_path/"data"),"XDG_CONFIG_HOME":str(tmp_path/"config"),
            "XDG_CACHE_HOME":str(tmp_path/"cache")})
    output = result.stdout + result.stderr
    (tmp_path / "godot.log").write_text(output)
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "ERROR:" not in output, output
    assert "IDLE_RENDERING_FAILURES:0" in output, output

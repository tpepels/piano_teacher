"""Phase C native notation and safe fallback acceptance."""
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

def test_phase_c_native_renderer_and_global_collision_scale():
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    proc = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/phase_c_notation.gd")],
        text=True, capture_output=True, timeout=60)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "PHASE_C_NOTATION_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output

def test_native_mode_is_opt_in_and_unsupported_music_reverts_to_legacy():
    app = (ROOT / "godot" / "main.gd").read_text()
    native = (ROOT / "godot" / "score_native_notation.gd").read_text()
    geometry = (ROOT / "godot" / "score_notation_geometry.gd").read_text()
    # Resume development of the existing native engine. The original
    # public flag must select it; the separate raster experiment is opt-in.
    assert 'PIANO_TEACHER_NATIVE_NOTATION") == "1"' in app
    assert 'OS.get_cmdline_user_args().has("--native-notation")' in app
    assert 'PIANO_TEACHER_NATIVE_NOTATION_EXPERIMENTAL' in app
    assert 'PIANO_TEACHER_EXACT_VEROVIO_GRID") == "1"' in app
    assert 'not native_notation_enabled' in app
    assert 'var retired_native_flag' not in app
    assert 'timeline_preview = (NativeNotation.new() if native_notation_enabled' in app
    assert 'timeline_model_request.request(URL + "/score/model")' in app
    assert 'timeline_preview.visible = false' in app
    assert 'push_warning("Native notation fallback: "' in app
    assert 'timeline.screen_x(' in native
    assert 'ordered_events = timeline.model.get("notation_events", []).duplicate()' in native
    assert 'for event in _visible_events(left, right):' in native
    assert 'cached_staff_gap' in native
    assert 'tie_pairs' in native
    assert 'str(int(meter[0]))' in native and 'str(int(meter[1]))' in native
    assert 'str(meter[0])' not in native and 'str(meter[1])' not in native
    assert 'str(int(measure.get("number", 0)))' in native
    assert 'draw_colored_polygon(' in native
    assert 'preload("res://score_strip.gd")' not in native
    assert 'preload("res://score_motion_curve.gd")' not in native
    assert 'MIN_ATTACK_SEPARATION' in geometry
    assert 'supported(model: Dictionary)' in geometry

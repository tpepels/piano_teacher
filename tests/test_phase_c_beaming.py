"""Phase C2 group-beam geometry and constant-axis regression."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_native_eighth_sixteenth_beams_in_simple_and_compound_meters():
    binary = shutil.which("godot") or shutil.which("godot4")
    if binary is None:
        pytest.skip("Godot 4 unavailable")
    result = subprocess.run([
        binary, "--headless", "--path", str(ROOT / "godot"),
        "--script", str(ROOT / "tests/godot/phase_c_beaming.gd"),
    ], capture_output=True, text=True, timeout=45)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "PHASE_C2_BEAM_FAILURES:0" in output, output
    assert "Parse Error:" not in output and "SCRIPT ERROR:" not in output, output


def test_beaming_uses_semantic_beat_and_never_verovio_x():
    geometry = (ROOT / "godot/notation/native/geometry.gd").read_text()
    renderer = (ROOT / "godot/notation/native/view.gd").read_text()
    assert "static func beam_groups(model: Dictionary)" in geometry
    assert "static func beat_group_length(meter: Array)" in geometry
    assert "func _paint_beams(data: Dictionary, gap: float)" in renderer
    index = (ROOT / "godot/notation/native/score_index.gd").read_text()
    assert 'var beam_groups: Array = source_beams.get("groups",[])' in index
    assert 'var index: Dictionary = ScoreIndex.build(timeline.model, glyphs)' in renderer
    assert "glyphs.beam_metadata" in renderer
    assert "Geometry.beam_groups(timeline.model)" not in renderer
    assert 'timeline.screen_x(float(event.get("beat", 0.0))' in renderer
    assert 'score_motion_curve.gd' not in renderer

"""Native notation, authentic source assets and collision-scale acceptance."""
import shutil
import subprocess
import os
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
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
        text=True, capture_output=True, timeout=60)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "PHASE_C_NOTATION_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output

def test_native_view_uses_authentic_source_assets_and_indexed_notation():
    app = (ROOT / "godot" / "main.gd").read_text()
    native = (ROOT / "godot" / "notation/native/view.gd").read_text()
    geometry = (ROOT / "godot" / "notation/native/geometry.gd").read_text()
    index = (ROOT / "godot/notation/native/score_index.gd").read_text()
    preparation = (ROOT / "piano_teacher/application/score_preparation.py").read_text()
    assert 'timeline.screen_x(' in native
    assert 'var index: Dictionary = ScoreIndex.build(timeline.model, glyphs)' in native
    assert 'var ordered_events: Array = model.get("notation_events", []).duplicate()' in index
    assert 'for event in _visible_events(left, right):' in native
    assert 'cached_staff_gap' in native
    assert 'tie_pairs' in native
    assert '_paint_meter_number(int(meter[0])' in native
    assert '_paint_meter_number(int(meter[1])' in native
    assert 'glyphs.paint(self, "head_black"' in native
    assert 'glyphs.paint(self, "rest_" + note_type' in native
    assert 'glyphs.paint(self, name' in native
    assert 'func _paint_ellipse(' not in native
    assert 'func _paint_flag(' not in native
    assert 'glyphs.paint_note_stem(' in native
    assert 'draw_arc(' not in native
    assert 'draw_circle(' not in native
    assert 'def native_glyphs' in (ROOT / "piano_teacher/notation/assets/glyphs.py").read_text()
    assert 'from ..notation.assets.glyphs import native_glyphs, preparation_symbols' in preparation
    assert 'parsed.get("native_glyphs", {})' in app
    assert 'parsed.get("native_chord_templates", {})' in app
    assert 'glyphs.paint_note(self, kind, normal_up, x, y, gap, ink)' in native
    assert 'note_templates(cache)' in preparation
    assert 'assemble_layout(source_score, native_notes=True,' in (
        ROOT / "piano_teacher/server.py").read_text()
    assert 'str(int(measure.get("number", 0)))' in native
    assert 'func _beam_segment(' not in native
    assert 'glyphs.paint_beam(' in native
    assert 'preload("res://notation/legacy/strip.gd")' not in native
    assert 'preload("res://notation/legacy/motion_curve.gd")' not in native
    assert 'MIN_ATTACK_SEPARATION' in geometry
    assert 'supported(model: Dictionary)' in geometry

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
    layout = (ROOT / "godot/notation/native/score_layout.gd").read_text()
    symbols = (ROOT / "godot/notation/native/symbol_painter.gd").read_text()
    context = (ROOT / "godot/notation/native/context_painter.gd").read_text()
    renderers = native+symbols+context
    preparation = (ROOT / "piano_teacher/application/score_preparation.py").read_text()
    assert 'timeline.screen_x(' in native
    assert 'var index: Dictionary = ScoreIndex.build(timeline.model, glyphs)' in layout
    assert 'var ordered_events: Array = model.get("notation_events", []).duplicate()' in index
    assert 'foreventin_visible_events(left,right,frame):' in ''.join(native.split())
    assert 'cached_staff_gap' in layout
    assert 'tie_pairs' in layout and 'score_layout.tie_pairs' in symbols
    assert 'paint_meter_number(canvas,frame,int(meter[0])' in context
    assert 'paint_meter_number(canvas,frame,int(meter[1])' in context
    assert 'glyphs.paint(canvas, "head_black"' in symbols
    assert 'glyphs.paint(canvas, "rest_" + note_type' in symbols
    assert 'glyphs.paint(canvas, name' in symbols
    assert 'func _paint_ellipse(' not in renderers
    assert 'func _paint_flag(' not in renderers
    assert 'func paint_flag(' not in renderers
    assert 'func paint_ellipse(' not in renderers
    assert 'glyphs.paint_note_stem(' in symbols
    assert 'draw_arc(' not in renderers
    assert 'draw_circle(' not in renderers
    assert 'def native_glyphs' in (ROOT / "piano_teacher/notation/assets/glyphs.py").read_text()
    assert 'from ..notation.assets.glyphs import native_glyphs, preparation_symbols' in preparation
    assert 'parsed.get("native_glyphs", {})' in app
    assert 'parsed.get("native_chord_templates", {})' in app
    assert 'glyphs.paint_note(canvas, kind, normal_up, x, y, gap, ink)' in symbols
    assert 'note_templates(cache)' in preparation
    assert 'score_preparation.assemble_layout(score, native_notes=True,' in (
        ROOT / "piano_teacher/application/score_artifacts.py").read_text()
    assert 'self.score_artifacts.geometry(self._score_selection(), native_notes=native_notes)' in (
        ROOT / "piano_teacher/server.py").read_text()
    assert 'str(int(measure.get("number",0)))' in ''.join(native.split())
    assert 'func _beam_segment(' not in renderers
    assert 'func beam_segment(' not in renderers
    assert 'glyphs.paint_beam(' in symbols
    assert 'preload("res://notation/legacy/strip.gd")' not in renderers
    assert 'preload("res://notation/legacy/motion_curve.gd")' not in renderers
    assert 'MIN_ATTACK_SEPARATION' in geometry
    assert 'supported(model: Dictionary)' in geometry

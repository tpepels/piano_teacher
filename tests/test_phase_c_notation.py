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
    painters = native + (ROOT / "godot/notation/native/render_pass.gd").read_text() + (ROOT / "godot/notation/native/source_pass_painter.gd").read_text()
    assert 'timeline.screen_x(' in painters  # screen mapping moved from view.gd into the pass painters
    assert 'var index: Dictionary = ScoreIndex.build(timeline.model, glyphs)' in layout
    assert 'var ordered_events: Array = model.get("notation_events", []).duplicate()' in index
    # Only indexed, viewport-visible events are visited (source_pass_painter, event_window.gd).
    assert 'foreventinEventWindow.visible(layout.ordered_events,left,right,frame):' in ''.join(
        (ROOT / "godot/notation/native/source_pass_painter.gd").read_text().split())
    assert 'cached_staff_gap' in layout
    assert 'tie_pairs' in layout and 'visible_source_spans(' in symbols and '"ties"' in symbols
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
    # Playhead dot/pulse circles in view.gd are the only allowed ones; the exact
    # rule lives in test_notation_symbols (owner decision: no rings on noteheads).
    assert 'draw_arc(' not in symbols+context
    assert 'draw_circle(' not in symbols+context
    assert 'def native_glyphs' in (ROOT / "piano_teacher/notation/assets/glyphs.py").read_text()
    assert 'from ..notation.assets.glyphs import native_glyphs, preparation_symbols' in preparation
    assets = (ROOT / "godot" / "native_score_assets.gd").read_text()  # asset parsing moved out of main.gd
    assert 'source.get("native_glyphs", {})' in assets
    assert 'source.get("native_chord_templates", {})' in assets
    assert 'glyphs.paint_note(canvas, kind, normal_up, x, y, gap, ink)' in symbols
    assert 'note_templates(cache)' in preparation
    assert 'score_preparation.assemble_layout(score,' in (
        ROOT / "piano_teacher/application/score_artifacts.py").read_text()
    assert 'artifacts.geometry(selection)' in (
        ROOT / "piano_teacher/server.py").read_text()
    assert 'str(int(measure.get("number",0)))' in ''.join(painters.split())
    assert 'func _beam_segment(' not in renderers
    assert 'func beam_segment(' not in renderers
    assert 'paint_beams(' in painters and 'func paint_beam(' in (ROOT / 'godot/notation/native/glyphs.gd').read_text()
    assert 'preload("res://notation/legacy/strip.gd")' not in renderers
    assert 'preload("res://notation/legacy/motion_curve.gd")' not in renderers
    assert 'MIN_ATTACK_SEPARATION' in geometry
    assert 'supported(model: Dictionary)' in geometry

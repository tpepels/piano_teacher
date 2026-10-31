"""Retained notation is compiled once and translated independently of transport."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_frame_path_never_reassembles_source_or_preparation_ink():
    view = (ROOT/"godot/notation/native/view.gd").read_text()
    draw = view.split("func _draw() -> void:", 1)[1].split(
        "\nfunc ",1)[0]
    assert "_paint_source_pass(" not in draw
    assert "symbols.paint_" not in draw
    assert "context_painter.paint_" not in draw
    assert "_place_retained_score(" in draw
    assert "retained_annotations.queue_redraw()" in draw
    assert "RetainedNoteProjection.append_visible(" in view
    assert "retained_ready()" in view
    assert 'call_deferred("emit_signal","retained_ink_compiled")' in view
    assert "SourcePassPainter.paint(self,canvas,variant,context)" in view
    source = (ROOT/"godot/notation/native/source_pass_painter.gd").read_text()
    assert 'if variant == "recovery"' in source
    assert "symbols.paint_beams(" in source
    assert "symbols.paint_beams(" not in draw
    assert "_paint_source_pass" not in view
    assert "RETAINED_POOL_SIZE" not in view
    assert "_required_repeat_copies()" in view
    session = (ROOT/"godot/score_asset_session.gd").read_text()
    assert 'renderer.connect("retained_ink_compiled",_finish_native_score)' in session
    assert 'not _renderer.retained_ready()' in session


@pytest.mark.skipif(shutil.which("godot") is None and
                    shutil.which("godot4") is None,
                    reason="Godot unavailable")
def test_moving_retained_score_does_not_repaint_it():
    binary = shutil.which("godot") or shutil.which("godot4")
    result = subprocess.run(
        [binary, "--headless", "--path", str(ROOT/"godot"),
         "--script", str(ROOT/"tests/godot/retained_segments.gd")],
        capture_output=True, text=True, timeout=25)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "RETAINED_SEGMENT_FAILURES:0" in output, output


@pytest.mark.skipif(shutil.which("godot") is None and
                    shutil.which("godot4") is None,
                    reason="Godot unavailable")
def test_retained_note_spatial_index_and_identity():
    binary = shutil.which("godot") or shutil.which("godot4")
    result = subprocess.run(
        [binary, "--headless", "--path", str(ROOT/"godot"),
         "--script", str(ROOT/"tests/godot/retained_note_projection.gd")],
        capture_output=True, text=True, timeout=20)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "RETAINED_NOTE_PROJECTION_FAILURES:0" in output, output


def test_fingering_overlay_has_bounded_source_window():
    source = (ROOT/"godot/notation/native/fingering_annotations.gd").read_text()
    assert "fingering_layout.sort_custom(" in source
    assert "widest_fingering" in source
    assert "for index in range(low,fingering_layout.size()):" in source
    assert "for item in fingering_layout:" not in source.split(
        "func paint(",1)[1].split("\nfunc ",1)[0]

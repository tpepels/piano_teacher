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
    assert "drawn_note_instances.append(" in view
    assert "retained_ready()" in view
    assert "retained_ink_compiled.emit()" in view
    assert 'retained_variant == "recovery"' in view
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

"""Bounded headless proof that static beam/slur masks preserve source geometry."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_prepared_engraving_has_no_live_beam_or_slur_assembly():
    compositor = (ROOT/"godot/notation/native/symbol_painter.gd").read_text()
    connector = (ROOT/"godot/notation/native/connector_geometry.gd").read_text()
    view = (ROOT/"godot/notation/native/view.gd").read_text()
    assert "score_layout.glyphs.paint_beam(canvas" not in compositor
    assert "score_layout.glyphs.paint_slur(canvas" not in compositor
    assert "prewarm_beam_layout" in view
    assert "prewarm_slur_geometry" in view
    assert "BeamSpritePlan.build" in connector
    assert "SlurSpritePlan.build" in connector


@pytest.mark.skipif(shutil.which("godot") is None and
                    shutil.which("godot4") is None,
                    reason="Godot unavailable")
def test_source_beam_and_slur_plans_match_verovio_coordinates():
    binary = shutil.which("godot") or shutil.which("godot4")
    result = subprocess.run(
        [binary, "--headless", "--path", str(ROOT/"godot"),
         "--script", str(ROOT/"tests/godot/prepared_sprite_plans.gd")],
        capture_output=True, text=True, timeout=20)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "PREPARED_SPRITE_PLAN_FAILURES:0" in output, output

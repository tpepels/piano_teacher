"""Native tuplet/double-dot rendering and semantic timing regression."""
from pathlib import Path
import shutil
import subprocess
import os

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_phase_c3_tuplets_and_double_dots():
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot is not installed")
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/phase_c_tuplets.gd")],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
        capture_output=True, text=True, timeout=50)
    logs = result.stdout + result.stderr
    assert result.returncode == 0, logs
    assert "PHASE_C3_TUPLET_FAILURES:0" in logs, logs
    assert "SCRIPT ERROR:" not in logs and "Parse Error:" not in logs, logs


def test_group_brackets_are_not_based_on_verovio_coordinates():
    geom = (ROOT / "godot/notation/native/geometry.gd").read_text()
    score = (ROOT / "godot/notation/native/view.gd").read_text()
    model = (ROOT / "piano_teacher/notation/model.py").read_text()
    assert "static func tuplet_groups(model: Dictionary)" in geom
    assert "static func valid_modification(event: Dictionary)" in geom
    assert "func _paint_tuplet_brackets(" in score
    assert "timeline.screen_x(" in score
    assert '"tuplet_marks"' in model
    assert "if int(event.get(\"dots\", 0)) < 0" in geom

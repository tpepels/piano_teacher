"""Real Godot regression for beat-lit practice and readable count-in."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_beat_synchronized_game_stage_and_readable_countdown():
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/phase78_stage.gd")],
        capture_output=True, text=True, timeout=40)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "PHASE78_FAILURES:0" in output, output

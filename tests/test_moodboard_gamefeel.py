"""Godot regression for the moodboard-style score and earned visual progress."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")

@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_moodboard_instrument_and_animation_progress():
    cmd = [GODOT, "--headless", "--path", str(ROOT / "godot"),
           "--script", str(ROOT / "tests/godot/moodboard_gamefeel.gd")]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "MOODBOARD_GAMEFEEL_FAILURES:0" in output, output

"""Real-Godot stress check for phase 8I bounded engraved texture residency."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_rapid_seeks_keep_only_current_gpu_tiles_and_survive_bad_buffers():
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/tile_residency.gd")],
        capture_output=True, text=True, timeout=35)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "TILE_RESIDENCY_FAILURES:0" in output, output

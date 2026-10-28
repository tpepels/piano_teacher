"""Fingering collision packing stays independent of native engraving."""
import shutil
import subprocess
from pathlib import Path
import pytest


def test_fingering_spatial_layout_headless():
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [godot, "--headless", "--path", str(root/"godot"),
         "--script", str(root/"tests/godot/fingering_spatial_layout.gd")],
        capture_output=True, text=True, timeout=20)
    log = result.stdout+result.stderr
    assert result.returncode == 0, log
    assert "SCRIPT ERROR" not in log, log
    assert "FINGERING_SPATIAL_FAILURES:0" in log, log

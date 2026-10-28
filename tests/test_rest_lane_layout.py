"""Polyphonic rest lanes remain independent of the native painter."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_native_rest_lane_layout_headless():
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [godot, "--headless", "--path", str(root/"godot"),
         "--script", str(root/"tests/godot/rest_lane_layout.gd")],
        capture_output=True, text=True, timeout=15)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "REST_LANE_LAYOUT_FAILURES:0" in output, output

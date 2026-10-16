"""Headless Godot measurement contract for phase 8D frame timing."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_frame_meter_reports_actual_intervals_without_adding_gameplay():
    result = subprocess.run([
        GODOT, "--headless", "--path", str(ROOT / "godot"),
        "--script", str(ROOT / "tests/godot/frame_meter.gd")],
        capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "FRAME_METER_FAILURES:0" in output, output

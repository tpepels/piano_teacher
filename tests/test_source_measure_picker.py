"""Source picker is an independent Godot control, not a main-scene helper."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_source_measure_picker_headless():
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot 4 not installed")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [godot, "--headless", "--path", str(root/"godot"),
         "--script", str(root/"tests/godot/source_measure_picker.gd")],
        capture_output=True, text=True, timeout=40)
    logs = result.stdout+result.stderr
    assert result.returncode == 0, logs
    assert "SCRIPT ERROR" not in logs, logs
    assert "SOURCE_PICKER_FAILURES:0" in logs, logs

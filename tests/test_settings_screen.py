"""Settings UI remains constructible without the main application controller."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_settings_screen_headless():
    executable = shutil.which("godot") or shutil.which("godot4")
    if executable is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [executable, "--headless", "--path", str(root/"godot"),
         "--script", str(root/"tests/godot/settings_screen.gd")],
        capture_output=True, text=True, timeout=20)
    log = result.stdout+result.stderr
    assert result.returncode == 0, log
    assert "SCRIPT ERROR" not in log, log
    assert "SETTINGS_SCREEN_FAILURES:0" in log, log

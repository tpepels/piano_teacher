"""Reachable recent music and saved-practice continuation in actual Godot UI."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
@pytest.mark.parametrize("resolution", ["800x600", "1024x768", "1280x800", "1536x960"])
def test_library_continues_the_actual_saved_piece(tmp_path, resolution):
    import os
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/library_resume.gd"), "--", resolution],
        capture_output=True, text=True, timeout=30, env=env,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "LIBRARY_RESUME_FAILURES:0" in output, output

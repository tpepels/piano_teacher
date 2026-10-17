"""Navigation intent survives pending controls and stale state polls."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
@pytest.mark.parametrize("scenario", [
    "start_settings", "start_lesson", "resume_settings", "resume_lesson",
    "start_library", "start_home", "response_before_poll", "stop_overrides_pause",
    "failure_flushes_intent", "quick_music_click", "picker_modal",
])
def test_navigation_survives_pending_control(scenario, tmp_path):
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/pending_navigation.gd"), "--", scenario],
        capture_output=True, text=True, timeout=30, env=env,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "PENDING_NAVIGATION_FAILURES:0" in output, output

"""Exercise actual Godot controls, keyboard commands, navigation and layout.

These catch accidental stop-on-pause, lost practice position on short detours,
incorrect Settings return destinations, and clipped connection guidance.
"""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
@pytest.mark.parametrize("scenario", [
    "primary_transport", "secondary_stop", "focused_shortcuts", "practice_detours",
    "settings_back_origin", "abandon_practice", "compact_feedback",
])
def test_actual_practice_interactions(scenario, tmp_path):
    # Isolate any Godot user settings from the real desktop session.
    import os
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/practice_interactions.gd"), "--", scenario],
        capture_output=True, text=True, timeout=30, env=env,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "PRACTICE_INTERACTION_FAILURES:0" in output, output

"""Run the actual contextual hint keyboard in Godot, including rendered pixels."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
@pytest.mark.parametrize("desktop", [False, True], ids=["layout", "rendered"])
def test_contextual_keyboard_preserves_pitch_identity_and_readable_registers(tmp_path, desktop):
    if desktop and not os.environ.get("DISPLAY"):
        pytest.skip("Rendered keyboard requires an X11 desktop")
    display = ["--display-driver", "x11", "--audio-driver", "Dummy"] if desktop else ["--headless"]
    result = subprocess.run(
        [GODOT, *display, "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/hint_keyboard.gd"), "--", str(tmp_path),
         "rendered" if desktop else "layout"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "XDG_DATA_HOME": str(tmp_path / "data"),
             "XDG_CONFIG_HOME": str(tmp_path / "config")},
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "HINT_KEYBOARD_FAILURES:0" in output, output

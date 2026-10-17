"""Check settled controls, clipping ancestors and usable list viewports."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("resolution", ["1536x960", "1280x800", "1024x768", "800x600"])
def test_drawer_contents_and_lesson_list_are_accessible(resolution):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/recovery_layout.gd"), "--", resolution],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RECOVERY_LAYOUT_FAILURES:0" in result.stdout

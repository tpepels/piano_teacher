"""Native polyphonic columns are calculated independently of the painter."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_native_voice_layout_with_real_godot():
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [godot,"--headless","--path",str(root/"godot"),
         "--script",str(root/"tests/godot/native_voice_layout.gd")],
        capture_output=True,text=True,timeout=40)
    output = result.stdout+result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "VOICE_LAYOUT_FAILURES:0" in output, output

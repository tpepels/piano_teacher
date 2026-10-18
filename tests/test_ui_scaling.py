"""The complete UI scales once from logical units, including custom controls."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_proportional_ui_scaling_and_resize_are_consistent(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"),
         "--audio-driver", "Dummy", "--script", str(ROOT / "tests/godot/ui_scaling.gd"),
         "--", str(tmp_path)], capture_output=True, text=True, timeout=45,
    )
    transcript = result.stdout + result.stderr
    (tmp_path / "godot.log").write_text(transcript)
    assert result.returncode == 0, transcript
    assert "SCRIPT ERROR" not in transcript and "ERROR:" not in transcript, transcript
    assert "UI_SCALING_FAILURES:0" in transcript, transcript

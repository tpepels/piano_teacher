"""Visual system regression tested in the actual Godot theme runtime."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")

@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_unified_visual_tokens_and_controls():
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/visual_system.gd")],
        capture_output=True, text=True, timeout=45,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "VISUAL_SYSTEM_FAILURES:0" in output, output

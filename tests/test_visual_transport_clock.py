"""Phase 7.6a: verify the GDScript clock against jittery real transport samples."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_constant_bpm_projection_survives_poll_jitter_and_pause():
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/visual_transport_clock.gd")],
        cwd=ROOT, capture_output=True, text=True, timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "VISUAL_TRANSPORT_CLOCK_FAILURES:0" in result.stdout, result.stdout

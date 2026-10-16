"""Phase 8B: a real Godot execution checks bounded Listen audio drift."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_listen_drift_correction_requires_sustained_mismatch():
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/listen_sync.gd")],
        capture_output=True, text=True, timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "LISTEN_SYNC_FAILURES:0" in output, output

"""The real practice transform fits complete notation and stays stable on Start/Pause."""
from pathlib import Path
import shutil
import subprocess

import pytest

from test_recovery_motion import make_midi_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_complete_engraving_fits_and_transport_keeps_zoom(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    make_midi_fixture(tmp_path, "chords", "both")
    result = subprocess.run([godot, "--headless", "--path", str(ROOT / "godot"),
                             "--script", str(ROOT / "tests/godot/practice_score_bounds.gd"),
                             "--", str(tmp_path)], capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "SCORE_BOUNDS_FAILURES:0" in result.stdout

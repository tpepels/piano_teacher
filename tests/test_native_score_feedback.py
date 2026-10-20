"""Earned feedback must follow exact native noteheads, never raster coordinates."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]

def test_feedback_tracks_native_identity_and_suppresses_ungraded_rewards():
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/native_score_feedback.gd")],
        capture_output=True, text=True, timeout=30)
    transcript = result.stdout + result.stderr
    assert result.returncode == 0, transcript
    assert "SCRIPT ERROR" not in transcript, transcript
    assert "NATIVE_FEEDBACK_FAILURES:0" in transcript, transcript

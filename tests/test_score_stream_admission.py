"""Future-only native score admission is checked by the real Godot policy."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_native_announced_empty_strip_is_future_only_and_peer_safe():
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot 4 unavailable")
    result = subprocess.run([
        godot, "--headless", "--path", str(ROOT / "godot"),
        "--script", str(ROOT / "tests/godot/score_stream_admission.gd")
    ], capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
    assert "SCORE_STREAM_ADMISSION_FAILURES:0" in output, output

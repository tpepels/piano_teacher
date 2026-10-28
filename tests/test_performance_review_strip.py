"""Settled performance UI is a standalone control and emits review snapshots."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_performance_review_strip_headless():
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot 4 not available")
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [godot, "--headless", "--path", str(root/"godot"),
         "--script", str(root/"tests/godot/performance_review_strip.gd")],
        capture_output=True, text=True, timeout=15)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "PERFORMANCE_REVIEW_STRIP_FAILURES:0" in output, output

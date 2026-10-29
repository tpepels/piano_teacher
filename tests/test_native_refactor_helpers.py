"""Exercise the extracted Godot drawer, score visibility and readiness helpers."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_native_refactor_helpers_with_real_godot():
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [godot, "--headless", "--path", str(root / "godot"),
         "--script", str(root / "tests/godot/native_refactor_helpers.gd")],
        capture_output=True, text=True, timeout=25)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "ERROR:" not in output, output
    assert "NATIVE_REFACTOR_FAILURES:0" in output, output

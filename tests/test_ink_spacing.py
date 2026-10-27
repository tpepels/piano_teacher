"""Focused headless regression for the pure native spacing policy."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_native_ink_spacing_is_global_and_collision_aware():
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        pytest.skip("Godot 4 unavailable")
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/ink_spacing.gd")],
        capture_output=True, text=True, timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "INK_SPACING_FAILURES:0" in output, output

"""Bounded rigid-source placement and score-wide spanner culling."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_native_source_displacement_budget_and_long_spanner_culling():
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    result = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/native_spacing_solver.gd")],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
        text=True, capture_output=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "NATIVE_SPACING_SOLVER_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output

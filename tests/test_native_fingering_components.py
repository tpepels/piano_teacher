"""Standalone native fingering extraction contract; no renderer is constructed."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_native_fingering_components_without_a_view():
    binary = shutil.which("godot") or shutil.which("godot4")
    if binary is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [binary, "--headless", "--path", str(root / "godot"),
         "--script", str(root / "tests/godot/native_fingering_components.gd")],
        capture_output=True, text=True, timeout=30,
    )
    output = run.stdout + run.stderr
    assert run.returncode == 0 and "SCRIPT ERROR" not in output and "ERROR:" not in output, output
    assert "FINGERING_COMPONENT_FAILURES:0" in output, output

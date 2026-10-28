"""Native pass/painter contracts with explicit data and no application or HTTP."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("contract", ["frame", "symbols", "context", "atlas"])
def test_native_paint_components_without_a_view(contract):
    binary = shutil.which("godot") or shutil.which("godot4")
    if binary is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [binary, "--headless", "--path", str(root / "godot"), "--script",
         str(root / "tests/godot/native_paint_components.gd"), "--", contract],
        capture_output=True, text=True, timeout=30,
    )
    output = run.stdout + run.stderr
    assert run.returncode == 0 and "SCRIPT ERROR" not in output and "ERROR:" not in output, output
    assert "PAINT_COMPONENT_FAILURES:0" in output, output

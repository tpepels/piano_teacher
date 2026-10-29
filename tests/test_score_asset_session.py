"""Score asset lifecycle contracts without Main, widgets or an HTTP server."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("contract", ["publication", "stale", "retry", "failure", "native"])
def test_score_asset_session_without_main(contract):
    binary = shutil.which("godot") or shutil.which("godot4")
    if binary is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [binary, "--headless", "--path", str(root / "godot"), "--script",
         str(root / "tests/godot/score_asset_session.gd"), "--", contract],
        capture_output=True, text=True, timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output and "ERROR:" not in output, output
    assert "SCORE_ASSET_SESSION_FAILURES:0" in output, output

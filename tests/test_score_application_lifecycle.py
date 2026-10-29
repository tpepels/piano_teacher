"""Native score HTTP ownership integrated into the actual application."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_main_uses_score_asset_session_for_stale_and_retry():
    binary = shutil.which("godot") or shutil.which("godot4")
    if binary is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [binary, "--headless", "--path", str(root / "godot"),
         "--audio-driver", "Dummy", "--script",
         str(root / "tests/godot/score_application_lifecycle.gd")],
        capture_output=True, text=True, timeout=25)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert not any(token in output
                   for token in ("SCRIPT ERROR", "Parse Error", "ERROR:")), output
    assert "SCORE_APPLICATION_FAILURES:0" in output, output

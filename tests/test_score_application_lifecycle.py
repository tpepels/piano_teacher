"""Native score typed request ownership integrated into the application."""
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
                   for token in ("SCRIPT ERROR", "Parse Error")), output
    # The fixture deliberately injects one genuine layout failure. It must
    # retain the production diagnostic while rejecting unrelated engine errors.
    assert [line for line in output.splitlines() if line.startswith("ERROR:")] == [
        "ERROR: SCORE_ASSET_FAILURE: Layout unavailable"], output
    assert "SCORE_APPLICATION_FAILURES:0" in output, output

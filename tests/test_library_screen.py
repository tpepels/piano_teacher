"""Library presentation runs independently; app tests replace only HTTP transport."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 unavailable")
@pytest.mark.parametrize("scenario", [
    "catalog_signals", "search_debounce", "health_rows", "errors_resize", "request_recovery",
    "snapshots", "empty_recent", "app_open_resume", "app_pending_failure", "app_open_failure_visible",
])
def test_library_owned_contract(scenario, tmp_path):
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CONFIG_HOME": str(tmp_path / "config"),
           "XDG_CACHE_HOME": str(tmp_path / "cache")}
    script = "library_application.gd" if scenario.startswith("app_") else "library_screen.gd"
    proc = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--audio-driver", "Dummy", "--script",
         str(ROOT / "tests/godot" / script), "--", scenario],
        capture_output=True, text=True, timeout=25, env=env)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    assert not any(token in output for token in ("SCRIPT ERROR", "Parse Error", "ERROR:")), output
    assert "LIBRARY_SCREEN_FAILURES:0" in output, output

"""Home presents captured library facts and emits navigation/open intent."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 unavailable")
@pytest.mark.parametrize("scenario", ["catalog", "recent_identity", "signals", "errors", "layout", "app_routes"])
def test_home_owned_contract(scenario, tmp_path):
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CONFIG_HOME": str(tmp_path / "config")}
    script = "home_application.gd" if scenario.startswith("app_") else "home_screen.gd"
    proc = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--audio-driver", "Dummy", "--script", str(ROOT / "tests/godot" / script), "--", scenario],
        capture_output=True, text=True, timeout=20, env=env)
    log = proc.stdout + proc.stderr
    assert proc.returncode == 0, log
    assert not any(token in log for token in ("SCRIPT ERROR", "Parse Error", "ERROR:")), log
    assert "HOME_SCREEN_FAILURES:0" in log, log

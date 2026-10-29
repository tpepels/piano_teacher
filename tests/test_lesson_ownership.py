"""Lesson panels and overview lifecycle have independent value/signal contracts."""
import os
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")

@pytest.mark.skipif(GODOT is None, reason="Godot 4 unavailable")
@pytest.mark.parametrize("scenario", ["overview", "choices", "reset", "layout", "selector", "cache", "retry", "stale_reset", "retry_regression", "listen_caption_regression", "app_routes"])
def test_lesson_ownership(scenario, tmp_path):
    script = "lesson_application.gd" if scenario == "app_routes" else "lesson_retry.gd" if scenario.endswith("_regression") else "lesson_ownership.gd"
    proc = subprocess.run([GODOT, "--headless", "--path", str(ROOT / "godot"),
        "--audio-driver", "Dummy", "--script", str(ROOT / "tests/godot" / script), "--", scenario],
        capture_output=True, text=True, timeout=20,
        env={**os.environ, "XDG_DATA_HOME":str(tmp_path / "data"), "XDG_CONFIG_HOME":str(tmp_path / "config")})
    log = proc.stdout + proc.stderr
    assert proc.returncode == 0, log
    assert not any(token in log for token in ("SCRIPT ERROR", "Parse Error", "ERROR:")), log
    assert "LESSON_FAILURES:0" in log, log

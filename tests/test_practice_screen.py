"""Practice presentation is usable without main, HTTP or native score assets."""
import os
from pathlib import Path
import shutil
import subprocess
import pytest
ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")

@pytest.mark.skipif(GODOT is None, reason="Godot 4 unavailable")
@pytest.mark.parametrize("scenario", ["captions", "signals", "score_gate", "source_picker", "midi_guard", "layout", "app_polling", "app_busy_ack"])
def test_independent_practice_screen(scenario, tmp_path):
    script = "practice_polling.gd" if scenario.startswith("app_") else "practice_screen.gd"
    proc = subprocess.run([GODOT,"--headless","--path",str(ROOT/"godot"),"--audio-driver","Dummy",
        "--script",str(ROOT/"tests/godot"/script),"--",scenario],
        capture_output=True,text=True,timeout=20,
        env={**os.environ,"XDG_DATA_HOME":str(tmp_path/"data"),"XDG_CONFIG_HOME":str(tmp_path/"config")})
    log=proc.stdout+proc.stderr
    assert proc.returncode == 0, log
    assert not any(token in log for token in ("SCRIPT ERROR","Parse Error","ERROR:")), log
    assert "PRACTICE_SCREEN_FAILURES:0" in log, log

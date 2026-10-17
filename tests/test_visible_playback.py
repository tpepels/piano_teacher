"""Exercise the ordinary launcher and real desktop pixels without MIDI input."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_launcher_moves_visible_notes_at_four_tempos(tmp_path):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Visible playback requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_visible_playback.py"),
         "--output-dir", str(tmp_path)], cwd=ROOT,
        capture_output=True, text=True, timeout=240,
    )
    assert result.returncode == 0, result.stdout + result.stderr + (
        (tmp_path / "godot.log").read_text(errors="replace")
        if (tmp_path / "godot.log").exists() else "")
    assert "VISIBLE_RESULT:PASS samples=44" in result.stdout

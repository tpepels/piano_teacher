"""The rendered timing line must stay fixed between throttled overlay frames."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from test_recovery_motion import make_midi_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_rendered_playhead_stays_fixed_on_every_moving_frame(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Graphical Godot required for pixel acceptance")
    make_midi_fixture(tmp_path, "chords", "both")
    result = subprocess.run([godot, "--display-driver", "x11", "--audio-driver", "Dummy",
                             "--path", str(ROOT / "godot"), "--script",
                             str(ROOT / "tests/godot/recovery_motion_capture.gd"),
                             "--", str(tmp_path), str(tmp_path),
                             "res://visual_transport_clock.gd", "--check"],
                            capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "RECOVERY_PLAYHEAD_FAILURES:0" in result.stdout

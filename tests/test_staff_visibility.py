"""Legacy raster continuity rails stay white outside preserved glyph columns."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from test_recovery_motion import make_midi_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_active_staves_are_white_through_countin_and_scrolling(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Graphical Godot required for staff pixel checks")
    for hand in ("right", "left", "both"):
        folder = tmp_path / hand
        folder.mkdir()
        make_midi_fixture(folder, "chords", hand)
    result = subprocess.run(
        [godot, "--path", str(ROOT / "godot"), "--audio-driver", "Dummy",
         "--script", str(ROOT / "tests/godot/staff_visibility.gd"), "--", str(tmp_path)],
        # The GDScript fixture explicitly selects the raster fallback; the
        # suite's native launch setting must not silently change that coverage.
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SCRIPT ERROR" not in result.stdout + result.stderr, result.stdout + result.stderr
    assert "STAFF_VISIBILITY_PIXEL_CHECKS:180" in result.stdout
    assert "STAFF_VISIBILITY_FAILURES:0" in result.stdout

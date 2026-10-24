"""Phase B deterministic Godot timeline acceptance; no PNG or MIDI device."""
from pathlib import Path
import shutil
import subprocess

import pytest
from test_phase1_camera import native_camera_run


ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"


def test_fixed_beat_timeline_and_preparation_at_40_80_120_bpm():
    binary = shutil.which("godot") or shutil.which("godot4")
    if binary is None:
        pytest.skip("Godot 4 not installed in this environment")
    result = subprocess.run([
        binary, "--headless", "--path", str(GODOT),
        "--script", str(ROOT / "tests/godot/phase_b_timeline.gd")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=45, check=False)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "PHASE_B_TIMELINE_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output, output


def test_native_app_uses_existing_visual_transport_clock(native_camera_run):
    report, _ = native_camera_run
    assert report["native_ready"] and report["clock_matched"]
    assert report["pause_frozen"] and report["resume_advanced"]
    assert report["lead_samples"] >= 2 and report["playing_samples"] >= 3

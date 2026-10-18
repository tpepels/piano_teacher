"""Phase B deterministic Godot timeline acceptance; no PNG or MIDI device."""
from pathlib import Path
import shutil
import subprocess

import pytest


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


def test_opt_in_app_uses_existing_visual_transport_clock_not_engraving_x():
    script = (GODOT / "main.gd").read_text()
    prototype = (GODOT / "score_timeline_preview.gd").read_text()
    timeline = (GODOT / "score_timeline.gd").read_text()
    assert 'timeline_model_request.request(URL + "/score/model")' in script
    assert 'timeline_preview.present(last_state, _transport_beat_now())' in script
    assert 'PIANO_TEACHER_TIMELINE_PREVIEW' in script
    assert 'PIANO_TEACHER_PIXELS_PER_BEAT' in timeline
    assert 'return beat * pixels_per_beat' in timeline
    assert 'return pixels_per_beat * bpm / 60.0' in timeline
    assert 'camera_clock, from)' in prototype
    assert 'Verovio' not in prototype

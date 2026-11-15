"""Cross-component musical spacing and forward tempo acceptance in actual Godot.

This catches different components introducing their own pixels-per-beat,
lookahead or staff-size defaults while retaining source-note beat identity.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 not installed")
def test_timing_geometry_scales_uniformly_through_mixed_meter_and_tempo():
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/timing_geometry_contract.gd")],
        cwd=ROOT, capture_output=True, text=True, timeout=60, check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
    assert "TIMING_GEOMETRY_FAILURES:0" in output, output


def test_spacing_policy_remains_a_pure_constant_owner():
    """No renderer, clock, or MIDI control belongs in the tuning constants."""
    source = (ROOT / "godot/notation/shared/spacing_policy.gd").read_text()
    assert source.startswith("extends RefCounted\n")
    assert "preload(" not in source and "func " not in source
    assert "var " not in source and "signal " not in source
    assert "DEFAULT_PIXELS_PER_BEAT := 96.0" in source
    for name in ("MAX_STAFF_GAP", "MIN_READABLE_STAFF_GAP",
                 "MIN_LOOKAHEAD_BEATS"):
        assert f"const {name} :=" in source

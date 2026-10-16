"""Headless presentation invariants for Phase 7.7."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_game_feel_requires_real_midi_event_for_hit(tmp_path):
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/phase77_reactions.gd")],
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PHASE77_FAILURES:0" in result.stdout, result.stdout + result.stderr

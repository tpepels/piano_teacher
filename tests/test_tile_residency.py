"""Native seeks bound visible work and reuse authentic atlas resources."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_rapid_seeks_reuse_native_atlas_and_recover_rejected_model(tmp_path):
    from piano_teacher.music import Note, Phrase
    from test_recovery_motion import make_phrase_fixture

    phrase = Phrase(1, 1, 80, 0, 320, tuple(
        Note(i, i + .5, 72 + i % 5, 0, 0, "right") for i in range(320)))
    make_phrase_fixture(tmp_path, phrase, boundaries=tuple(range(0,321,4)), hand="right")
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/tile_residency.gd"), "--", str(tmp_path)],
        capture_output=True, text=True, timeout=35)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "TILE_RESIDENCY_FAILURES:0" in output, output

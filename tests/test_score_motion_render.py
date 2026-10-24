"""Production native noteheads keep a fixed line and constant beat travel."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def make_render_fixture(folder, bars=2):
    from piano_teacher.music import Note, Phrase
    from test_recovery_motion import make_phrase_fixture

    duration = bars * 3
    notes = tuple(Note(i, i + .5, 77 - (i // 3) % 5, 0, 0, "right")
                  for i in range(duration))
    phrase = Phrase(1, 1, bars, 0, duration, notes)
    return make_phrase_fixture(folder, phrase, hand="right", bpm=68,
        boundaries=tuple(range(0, duration + 1, 3)), time_signatures=((0,3,4),))


@pytest.mark.parametrize("bars", [2, 40])
def test_actual_score_transforms_keep_fixed_line_and_exact_downbeat(tmp_path, bars):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 is unavailable")
    make_render_fixture(tmp_path, bars)
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/score_motion.gd"), "--", str(tmp_path)],
        capture_output=True, text=True, timeout=40)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "SCORE_MOTION_FAILURES:0" in output, output

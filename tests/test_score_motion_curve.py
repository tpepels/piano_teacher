"""Camera easing preserves timing while removing sudden short-note velocity jumps."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_smooth_score_motion_respects_real_beat_anchors():
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/notation/legacy/motion_curve.gd")],
        capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "SMOOTH_SCORE_FAILURES:0" in output, output


def test_introduction_does_not_duplicate_first_barline_or_follow_label():
    root = ROOT / "godot"
    overlay = (root / "score_overlay.gd").read_text(encoding="utf-8")
    stage = (root / "game_stage.gd").read_text(encoding="utf-8")
    assert "var bar_end: float = first_x" not in overlay
    assert "var safe_entry: float = minf(left, first_x - gap * 10.0)" in overlay
    assert '"Follow" if score_preview else "Play here"' not in stage
    assert 'draw_string(font, Vector2(flag.get_center()' not in stage

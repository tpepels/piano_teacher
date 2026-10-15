"""Real learner errors must lead to useful recovery and honest mastery."""
import os
import shutil

import pytest

from scripts.smoke_instructional_godot import run


def test_real_midi_learner_recovers_failed_bars_and_earns_three_full_target_passes(tmp_path):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Rendered instructional journey requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
    result = run(tmp_path)
    assert result["failures"] == []
    assert result["renderer"] != "headless"
    assert result["full_clean_tempos"] == [194,213,234,240,240,240]
    first, second = [frame for frame in result["frames"] if "errors-score-moving-" in frame["frame"]]
    assert first["note_id"] == second["note_id"]
    assert second["note_x"] < first["note_x"]-8
    assert abs(second["line_x"]-first["line_x"]) < 1
    assert result["frames"][-1]["mastered"] == 1
    assert len(result["frames"]) >= 25

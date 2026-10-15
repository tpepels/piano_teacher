"""One MIDI learner prepares, recovers, earns mastery and reviews real music."""
import os
import shutil

import pytest

from scripts.smoke_instructional_godot import run


def test_real_student_prepares_recovers_masters_listens_performs_and_revisits(tmp_path):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Rendered instructional journey requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
    result = run(tmp_path,finish_modes=True)
    assert result["failures"] == []
    assert result["renderer"] != "headless"
    assert result["full_clean_tempos"] == [194,213,234,240,240,240]
    first, second = [frame for frame in result["frames"] if "errors-score-moving-" in frame["frame"]]
    assert first["note_id"] == second["note_id"]
    assert second["note_x"] < first["note_x"]-8
    assert abs(second["line_x"]-first["line_x"]) < 1
    earned = next(frame for frame in result["frames"] if frame["frame"] == "28-next-original-variant.png")
    assert earned["mastered"] == 1 and earned["mode"] == "learn"
    assert result["earned_variant"]["source_notes"] == 32
    assert result["finished_modes"] and result["revisited_trouble"]
    assert result["performance_summary"]["total"] == result["performance_summary"]["missed"] == 32
    example = next(frame for frame in result["frames"] if frame["frame"] == "29-earned-original-listen.png")
    assert example["audio_playing"] and example["pcm_bytes"] > 10000
    assert result["frames"][-1]["mastered"] == 1
    assert len(result["frames"]) >= 25

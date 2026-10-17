"""Actual learning UI and pause choices must fit the learner's desktop."""
import os
import shutil

import pytest

from scripts.smoke_learning_ui import run


def test_real_learning_ui_at_three_sizes_fullscreen_and_all_pause_choices(tmp_path, monkeypatch):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Rendered learning UI requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
    from piano_teacher import sample_piano
    monkeypatch.setattr(sample_piano, "find_soundfont", lambda: None)
    result = run(tmp_path)
    assert result["failures"] == []
    assert result["renderer"] != "headless"
    assert any(frame["fullscreen"] and frame["pause_sheet"] for frame in result["frames"])
    for dimensions in ("1536x960","1024x768","800x600"):
        hint = next(frame for frame in result["frames"] if frame["frame"] == f"hinted-learn-{dimensions}.png")
        pause = next(frame for frame in result["frames"] if frame["frame"] == f"pause-sheet-{dimensions}.png")
        assert hint["notehead_ink"] >= 8 and hint["score_height"] >= 135
        assert pause["pause_sheet"] and len(pause["pause_controls"]) == 9
    assert result["frames"][-1]["screen"] == "library"

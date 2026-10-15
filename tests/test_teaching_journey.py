"""The real learner path must connect imported notes, hints and musical time."""
import os
import shutil

import pytest

from scripts.smoke_teaching_godot import run


def test_imported_midi_guided_hints_and_real_practice_keep_mastery_honest(tmp_path):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Rendered teaching journey requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
    result = run(tmp_path)
    assert result["failures"] == []
    assert result["renderer"] != "headless"
    hint = next(frame for frame in result["frames"] if frame["frame"] == "wrong-note-hint.png")
    assert hint["painted_expected_keys"] == 3
    assert hint["notehead_ink"] >= 8
    first, last = [frame for frame in result["frames"] if frame["frame"].startswith("practice-playing-")]
    assert last["note_x"] < first["note_x"] - 10

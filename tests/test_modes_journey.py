"""Downloaded example audio and uninterrupted performance remain honest modes."""
import os
import shutil

import pytest

from scripts.smoke_modes_godot import run


def test_real_listen_pcm_and_all_missed_perform_end_with_actionable_summary(tmp_path, monkeypatch):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Rendered mode journey requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
    from piano_teacher import sample_piano
    monkeypatch.setattr(sample_piano, "find_soundfont", lambda: None)
    result = run(tmp_path)
    assert result["failures"] == []
    assert result["renderer"] != "headless"
    assert result["wav"]["duration_seconds"] >= 4
    assert result["wav"]["nonzero_samples"] > 1000
    audio = next(frame for frame in result["frames"] if frame["frame"] == "02-listen-player-active.png")
    assert audio["audio_playing"] and audio["pcm_bytes"] > 10000
    assert result["performance_summary"]["accuracy_percent"] == 0
    assert result["frames"][-1]["mastered"] == 0

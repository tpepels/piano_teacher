"""Downloaded example audio and uninterrupted performance remain honest modes."""
import os
import shutil

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi
from scripts.smoke_modes_godot import make_fixture, run


def expected_route(piece):
    """Find the full-source connection exposed by the ordinary lesson picker."""
    plan = LearningPlan(piece)
    step = next(step for step in plan.lesson_steps if step.kind == "connect")
    plan.select_step(plan.lesson_steps.index(step) + 1)
    phrase = plan.active_phrase
    return (step.kind, step.first_bar, step.last_bar, step.level,
            step.required_notes, phrase.start, phrase.end,
            min(note.start for note in phrase.notes), max(note.end for note in phrase.notes))


def test_modes_fixture_full_connection_keeps_source_rests_and_held_ending(tmp_path):
    source = tmp_path / "modes.mid"
    make_fixture(source)
    assert expected_route(load_midi(source)) == ("connect", 1, 4, "original", 26, 0, 16, 1, 16)


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

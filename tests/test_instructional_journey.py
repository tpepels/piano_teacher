"""One MIDI learner prepares, recovers, earns mastery and reviews real music."""
import os
import shutil

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.learner_state import guided_units
from piano_teacher.music import load_midi
from scripts.smoke_instructional_godot import make_fixture, run


def expected_route(piece):
    """Inspect the real default route without starting a server or transport."""
    plan = LearningPlan(piece)
    return {
        "source_grid": piece.bar_boundaries,
        "stages": [(step.kind, step.first_bar, step.last_bar, step.level,
                    step.required_notes) for step in plan.lesson_steps],
        "guided_units": [(unit["start_beat"], unit["end_beat"], unit["required_notes"])
                         for unit in guided_units(plan.active_variant, piece.bar_boundaries)],
        "partial_attacks": sum(note.start >= piece.bar_boundaries[1]
                               for note in plan.active_variant.notes),
    }


def test_instructional_fixture_keeps_partial_retry_inside_default_two_measure_route(tmp_path):
    source = tmp_path / "lesson.mid"
    make_fixture(source)
    # A second-measure retry still has eight misses: the five-error recovery
    # threshold stays intact, and that partial cannot earn full-stage mastery.
    assert expected_route(load_midi(source)) == {
        "source_grid": (0, 8, 16),
        "stages": [("learn", 1, 2, "skeleton", 16),
                   ("learn", 1, 2, "original", 32)],
        "guided_units": [(0, 16, 16)],
        "partial_attacks": 8,
    }


def test_real_student_prepares_recovers_masters_listens_performs_and_revisits(tmp_path, monkeypatch):
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Rendered instructional journey requires a graphical desktop")
    if not (shutil.which("godot") or shutil.which("godot4")):
        pytest.skip("Godot unavailable")
    from piano_teacher import sample_piano
    monkeypatch.setattr(sample_piano, "find_soundfont", lambda: None)
    result = run(tmp_path,finish_modes=True)
    assert result["failures"] == []
    assert result["renderer"] != "headless"
    assert result["full_clean_tempos"] == [194,207,223,240,240,240]
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

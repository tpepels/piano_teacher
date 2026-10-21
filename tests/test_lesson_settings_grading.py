"""Numerical grading and count-in targets follow the versioned lesson policy."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from piano_teacher.lesson_settings import SETTINGS, load_lesson_settings
from piano_teacher import practice, lesson_timing
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import PlayedNote


def _phrase():
    note = Note(0.0, 1.0, 60, 0, 0, "right")
    return Phrase(1, 1, 1, 0.0, 4.0, (note,))


def test_onset_threshold_changes_grade_without_changing_source(monkeypatch):
    played = [PlayedNote(60, 0.15, 1.15)]
    assert practice.evaluate(_phrase(), "right", 60, played).notes[0].status == "late"
    monkeypatch.setattr(practice, "SETTINGS", replace(
        SETTINGS, grading_onset_tolerance_seconds=0.2))
    assert practice.evaluate(_phrase(), "right", 60, played).clean


def test_duration_threshold_changes_grade(monkeypatch):
    played = [PlayedNote(60, 0.0, 0.72)]
    assert practice.evaluate(_phrase(), "right", 60, played).notes[0].status == "short"
    monkeypatch.setattr(practice, "SETTINGS", replace(
        SETTINGS, grading_duration_tolerance_fraction=0.3))
    assert practice.evaluate(_phrase(), "right", 60, played).clean


def test_count_in_ceiling_is_loaded_from_committed_policy(monkeypatch):
    assert lesson_timing.lead_in_beats(4, 60) == 4
    monkeypatch.setattr(lesson_timing, "SETTINGS", replace(
        SETTINGS, count_in_max_seconds=2.0))
    assert lesson_timing.lead_in_beats(4, 60) == 2
    assert lesson_timing.lead_in_beats(4, 60, max_seconds=3.0) == 3


@pytest.mark.parametrize("key,value", [
    ("grading_onset_tolerance_seconds", -0.1),
    ("grading_duration_tolerance_fraction", 1.2),
    ("grading_duration_floor_seconds", 0),
    ("grading_match_window_min_seconds", 0.05),
    ("grading_match_window_beats", 0),
    ("count_in_max_seconds", 0),
])
def test_invalid_grading_settings_cannot_load(tmp_path, key, value):
    policy = json.loads((Path(__file__).parents[1] /
                         "piano_teacher/lesson_settings.json").read_text())
    policy[key] = value
    path = tmp_path / "bad-policy.json"
    path.write_text(json.dumps(policy))
    with pytest.raises(ValueError):
        load_lesson_settings(path)

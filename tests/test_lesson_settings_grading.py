"""Numerical grading and count-in targets follow the versioned lesson policy."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from piano_teacher.lesson_settings import SETTINGS, load_lesson_settings
from piano_teacher import practice, lesson_timing, grading_tolerance
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import PlayedNote


def _phrase():
    note = Note(0.0, 1.0, 60, 0, 0, "right")
    return Phrase(1, 1, 1, 0.0, 4.0, (note,))


def test_onset_threshold_changes_grade_without_changing_source(monkeypatch):
    played = [PlayedNote(60, 0.21, 1.21)]
    assert practice.evaluate(_phrase(), "right", 60, played).notes[0].status == "late"
    monkeypatch.setattr(grading_tolerance, "SETTINGS", replace(
        SETTINGS, grading_onset_tolerance_seconds=0.22))
    assert practice.evaluate(_phrase(), "right", 60, played).clean


def test_duration_threshold_changes_grade(monkeypatch):
    played = [PlayedNote(60, 0.0, 0.35)]
    assert practice.evaluate(_phrase(), "right", 60, played).notes[0].status == "short"
    monkeypatch.setattr(grading_tolerance, "SETTINGS", replace(
        SETTINGS, grading_duration_tolerance_fraction=0.6))
    assert practice.evaluate(_phrase(), "right", 60, played).clean


def test_count_in_is_one_full_bar_without_a_seconds_ceiling():
    # Owner decision 2026-11-08: the count-in is always a full bar; the
    # count_in_max_seconds policy key was removed.
    assert lesson_timing.lead_in_beats(4, 60) == 4
    assert lesson_timing.lead_in_beats(4, 20) == 4
    assert not hasattr(SETTINGS, "count_in_max_seconds")


def test_policy_file_with_the_retired_count_in_key_still_loads(tmp_path):
    policy = json.loads((Path(__file__).parents[1] /
                         "piano_teacher/lesson_settings.json").read_text())
    policy["count_in_max_seconds"] = 4
    path = tmp_path / "older-policy.json"
    path.write_text(json.dumps(policy))
    assert load_lesson_settings(path) == SETTINGS


def test_unknown_policy_keys_are_still_rejected(tmp_path):
    policy = json.loads((Path(__file__).parents[1] /
                         "piano_teacher/lesson_settings.json").read_text())
    policy["count_in_minimum_bars"] = 1
    path = tmp_path / "typo-policy.json"
    path.write_text(json.dumps(policy))
    with pytest.raises(ValueError):
        load_lesson_settings(path)


@pytest.mark.parametrize("key,value", [
    ("grading_onset_tolerance_seconds", -0.1),
    ("grading_duration_tolerance_fraction", 1.2),
    ("grading_duration_floor_seconds", 0),
    ("grading_match_window_min_seconds", 0.05),
    ("grading_match_window_beats", 0),
])
def test_invalid_grading_settings_cannot_load(tmp_path, key, value):
    policy = json.loads((Path(__file__).parents[1] /
                         "piano_teacher/lesson_settings.json").read_text())
    policy[key] = value
    path = tmp_path / "bad-policy.json"
    path.write_text(json.dumps(policy))
    with pytest.raises(ValueError):
        load_lesson_settings(path)

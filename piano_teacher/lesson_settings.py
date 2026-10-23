"""Commit this file's companion JSON to tune the lesson algorithm.

These are course rules, not UI preferences. Restart the Python backend after
editing lesson_settings.json; the loaded settings are stable for a session.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class LessonSettings:
    focus_measures: int
    focus_min_onsets: int
    focus_max_measures: int
    repeated_tempo_min_attacks: int
    start_tempo_bpm: int
    automatic_tempo_steps: int
    manual_tempo_step_bpm: int
    minimum_tempo_step_bpm: int
    minimum_bpm: int
    maximum_bpm: int
    clean_runs_to_master: int
    recovery_errors_in_window: int
    warmup_recovery_errors: int
    recovery_tempo_multiplier: float
    guided_recovery_after_failures: int
    feedback_seconds: float
    grading_onset_tolerance_seconds: float
    grading_duration_tolerance_fraction: float
    grading_duration_floor_seconds: float
    grading_match_window_min_seconds: float
    grading_match_window_beats: float
    count_in_max_seconds: float


def load_lesson_settings(path: Path | None = None) -> LessonSettings:
    path = Path(path) if path is not None else Path(__file__).with_name("lesson_settings.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected = set(LessonSettings.__dataclass_fields__)
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError(f"Lesson settings keys must match {sorted(expected)}")
    for key, spec in LessonSettings.__dataclass_fields__.items():
        value = raw[key]
        if spec.type in ("int", int):
            if type(value) is not int:
                raise ValueError(f"{key} must be an integer")
        elif type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number")
    data = LessonSettings(**raw)
    if (data.focus_measures < 1 or data.focus_min_onsets < 1
            or data.focus_max_measures < data.focus_measures
            or data.repeated_tempo_min_attacks < 1 or data.minimum_bpm < 1
            or data.maximum_bpm < data.minimum_bpm
            or data.clean_runs_to_master < 1 or data.manual_tempo_step_bpm < 1
            or data.minimum_tempo_step_bpm < 1
            or not data.minimum_bpm <= data.start_tempo_bpm <= data.maximum_bpm
            or data.automatic_tempo_steps < 1
            or data.recovery_errors_in_window < 1
            or data.warmup_recovery_errors < 1
            or data.guided_recovery_after_failures < 1
            or data.feedback_seconds < 0
            or data.grading_onset_tolerance_seconds <= 0
            or not 0 < data.grading_duration_tolerance_fraction <= 1
            or data.grading_duration_floor_seconds <= 0
            or data.grading_match_window_min_seconds < data.grading_onset_tolerance_seconds
            or data.grading_match_window_beats <= 0
            or data.count_in_max_seconds <= 0
            or not 0 < data.recovery_tempo_multiplier < 1):
        raise ValueError("Invalid lesson target, BPM limit, or adaptive tempo multiplier")
    return data


SETTINGS = load_lesson_settings()

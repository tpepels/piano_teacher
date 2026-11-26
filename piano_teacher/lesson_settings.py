"""Validated lesson tuning and explicitly scoped course rules.

The flat JSON format is retained for existing installations and developer tuning.
Its historical focus and mastery values belong to source-progression,
warm-ups and the Coda/Fukuda alternative. Practice Flow uses its own moving
window and two-clean-target-pass contract. These are not UI preferences.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path


# count_in_max_seconds: removed by the owner decision of 2026-11-08 (the
# count-in is always one full bar at any tempo).
RETIRED_KEYS = frozenset({"count_in_max_seconds"})


@dataclass(frozen=True)
class LessonSettings:
    focus_measures: int
    focus_min_onsets: int
    focus_max_attacks: int
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
    minimum_timing_accuracy_percent: float = 0.0


def load_lesson_settings(path: Path | None = None) -> LessonSettings:
    path = Path(path) if path is not None else Path(__file__).with_name("lesson_settings.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        # Retired policy keys still load; they no longer change anything.
        raw = {key: value for key, value in raw.items()
               if key not in RETIRED_KEYS}
        raw.setdefault("minimum_timing_accuracy_percent", 0.0)
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
            or data.focus_max_attacks < data.focus_min_onsets
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
            or not 0 <= data.minimum_timing_accuracy_percent <= 100
            or not 0 < data.recovery_tempo_multiplier < 1):
        raise ValueError("Invalid lesson target, BPM limit, or adaptive tempo multiplier")
    return data


SETTINGS = load_lesson_settings()


@dataclass(frozen=True, slots=True)
class CourseRules:
    """Resolved rules for one generator; never a mutable lesson progress owner."""

    name: str
    clean_runs_to_master: int
    focus_measures: int
    focus_min_onsets: int
    focus_max_measures: int
    focus_max_attacks: int
    recovery_errors_in_window: int


def course_rules() -> CourseRules:
    """Practice Flow's course rules (docs/practice-flow.md)."""
    from .application.practice_flow import CLEAN_TAKES_AT_TARGET
    from .practice_windows import MAX_PRACTICE_BARS
    return CourseRules(
        "practice-flow", CLEAN_TAKES_AT_TARGET, 1, 1, MAX_PRACTICE_BARS,
        SETTINGS.focus_max_attacks, SETTINGS.recovery_errors_in_window)


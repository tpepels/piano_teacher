"""A2 course-specific lesson policy is resolved from the active generator."""
from piano_teacher.application.practice_flow import CLEAN_TAKES_AT_TARGET
from piano_teacher.lesson_settings import SETTINGS, course_rules
from piano_teacher.practice_windows import MAX_PRACTICE_BARS


def test_practice_flow_uses_own_mastery_and_window_limits():
    selected = course_rules("practice-flow")
    assert selected.clean_runs_to_master == CLEAN_TAKES_AT_TARGET == 2
    assert selected.focus_measures == 1
    assert selected.focus_max_measures == MAX_PRACTICE_BARS == 4


def test_other_courses_keep_configured_three_pass_and_source_focus():
    for name in ("coda-fukuda-midi", "source-progression"):
        chosen = course_rules(name)
        assert chosen.clean_runs_to_master == SETTINGS.clean_runs_to_master
        assert chosen.focus_measures == SETTINGS.focus_measures
        assert chosen.focus_max_measures == SETTINGS.focus_max_measures
        assert chosen.focus_max_attacks == SETTINGS.focus_max_attacks


def test_warmups_use_their_own_recovery_threshold():
    chosen = course_rules("source-progression", warmup=True)
    assert chosen.clean_runs_to_master == SETTINGS.clean_runs_to_master
    assert chosen.recovery_errors_in_window == SETTINGS.warmup_recovery_errors
    assert course_rules("practice-flow").recovery_errors_in_window == (
        SETTINGS.recovery_errors_in_window)

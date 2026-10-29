"""Pure recovery escalation preserves engine tempo and restarts by source identity."""
from dataclasses import FrozenInstanceError
import pytest

from piano_teacher.application.rolling_recovery import plan_rolling_recovery
from piano_teacher.lesson_settings import SETTINGS
from piano_teacher.recovery import RecoveryDecision


def test_repeated_failure_is_escalated_only_for_exact_same_source_chunk():
    decision = RecoveryDecision(8., 4., 5, 2, 3)
    one = plan_rolling_recovery(
        decision, identity="stage-a", bpm=80,
        previous_key=None, previous_count=0,
        grid=(0., 4., 8.), first_bar=1, now=100.)
    assert one.trouble_key == ("stage-a", 4., 8.)
    assert one.trouble_count == 1
    assert one.bpm == max(SETTINGS.minimum_bpm,
                          round(80 * SETTINGS.recovery_tempo_multiplier))
    assert one.display.notice["to_bpm"] == one.bpm
    assert one.display.retry_range["start_beat"] == 4.
    assert one.display.notice["expires_at"] == 109.
    repeat = plan_rolling_recovery(
        decision, identity="stage-a", bpm=one.bpm,
        previous_key=one.trouble_key,
        previous_count=SETTINGS.guided_recovery_after_failures - 1,
        grid=(0., 4., 8.), first_bar=1, now=101.)
    assert repeat.guided
    assert "Learn bars" in repeat.display.next_action
    different = plan_rolling_recovery(
        decision, identity="stage-b", bpm=one.bpm,
        previous_key=repeat.trouble_key, previous_count=repeat.trouble_count,
        grid=(0., 4., 8.), first_bar=1, now=102.)
    assert different.trouble_count == 1
    assert not different.guided
    with pytest.raises(FrozenInstanceError):
        one.bpm = 123


def test_recovery_tempo_never_drops_below_configured_minimum():
    decision = RecoveryDecision(4., 0., 5, 0, 5)
    plan = plan_rolling_recovery(
        decision, identity="slow", bpm=SETTINGS.minimum_bpm,
        previous_key=None, previous_count=0,
        grid=(0., 4.), first_bar=7, now=30.)
    assert plan.bpm == SETTINGS.minimum_bpm
    assert plan.display.notice["first_bar"] == 7

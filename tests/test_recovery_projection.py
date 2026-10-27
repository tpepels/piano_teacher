"""Recovery presentation does not mutate MIDI, lesson, or engine state."""
from dataclasses import FrozenInstanceError
import pytest

from piano_teacher.recovery import RecoveryDecision
from piano_teacher.recovery_projection import recovery_display


def test_recovery_display_preserves_bounds_tempo_and_expiry():
    decision = RecoveryDecision(end_beat=8.0, restart_beat=4.0,
                                errors=5, wrong=2, missed=3)
    result = recovery_display(
        decision, grid=(0.0,4.0,8.0,12.0), first_bar=3,
        before_bpm=80, after_bpm=72, now=100.0, guided=False)
    assert result.notice == {
        "kind":"slowdown", "errors":5, "missed":3, "wrong":2,
        "from_bpm":80, "to_bpm":72,
        "first_bar":4, "last_bar":4, "expires_at":109.0}
    assert result.retry_range == {
        "first_bar":4, "last_bar":4, "start_beat":4.0, "end_beat":8.0}
    assert result.feedback == "5 wrong or missed notes - retrying from measure 4 at 72 BPM"
    assert result.next_action == "Retry bars 4-4 at 72 BPM."
    with pytest.raises(FrozenInstanceError):
        result.feedback = "changed"


def test_guided_escalation_uses_source_bar_grid_for_mixed_meter():
    decision=RecoveryDecision(end_beat=10.0,restart_beat=3.0,
                              errors=6, wrong=4, missed=2)
    result=recovery_display(
        decision, grid=(0.0,3.0,6.0,10.0,14.0), first_bar=1,
        before_bpm=90, after_bpm=81, now=50.0, guided=True)
    assert result.notice["first_bar"] == 2
    assert result.notice["last_bar"] == 3
    assert result.retry_range["first_bar"] == 2
    assert result.retry_range["last_bar"] == 3
    assert result.next_action == "Learn bars 2-3 slowly, then retry the rhythm."

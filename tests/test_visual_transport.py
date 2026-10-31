"""Visual transport owns clock/rewind state without importing the engine."""
import pytest

from piano_teacher.server import PracticeEngine
from piano_teacher.visual_transport import VisualTransport


def test_visual_transport_stop_resets_attempt_but_preserves_measure_gap():
    t = VisualTransport(_visual_rewind_seconds=1.2)
    t.visual_gap_beats = 3
    t.visual_offset_beats = 12
    t.paused = True
    t.paused_at = 99
    t.next_at = 200
    t.play_from_beat = 4
    t.schedule_preparation({"duration_beats":3}, source_from_beat=4,
                           from_visual=18, now=100, reverse_seconds=.5, bpm=60)
    t.reset_for_stop(rewind_seconds=1.2)
    assert t.visual_gap_beats == 3
    assert t.visual_offset_beats == 0 and t._visual_rewind_from is None
    assert t.practice_preparation is None and not t._preparation_pending
    assert t.play_from_beat == 0 and t.pending_rewind is None
    assert t.next_at == 0 and not t.paused and t.paused_at == 0
    assert t._visual_rewind_seconds == 1.2


def test_visual_transport_preparation_preserves_source_and_continuous_visual_axis():
    t = VisualTransport(_visual_rewind_seconds=1)
    t.visual_offset_beats = 8
    deadline = t.schedule_preparation(
        {"duration_beats":4}, source_from_beat=2,
        from_visual=15, now=100, reverse_seconds=2, bpm=60)
    assert deadline == pytest.approx(106)
    assert t.pending_rewind == 2
    assert t.practice_preparation["measure"]["start_beat"] == 6
    assert t.practice_preparation["measure"]["end_beat"] == 10
    assert t.practice_preparation["pass_start_beat"] == 8
    assert t.position(101, phrase_length=8, bpm=60, running=False,
                      pending_auto_result=False) == (10.5, -4.5, 6)
    t.begin_take(loop_continuation=True)
    assert t.practice_preparation["phase"] == "complete"
    assert t.pending_rewind is None and not t._preparation_pending
    t.begin_take(loop_continuation=False)
    assert t.practice_preparation is None


@pytest.mark.parametrize("shift_run_at", (False, True))
def test_resume_moves_each_active_deadline_by_the_same_paused_duration(shift_run_at):
    t = VisualTransport(run_at=90, visual_offset_beats=8)
    t.schedule_preparation({"duration_beats": 4}, source_from_beat=2,
        from_visual=15, now=100, reverse_seconds=2, bpm=60)
    t.pause(at=101)
    frozen = t.position(101, phrase_length=8, bpm=60, running=False,
                        pending_auto_result=False)
    t.resume(now=111, shift_run_at=shift_run_at)
    assert t.run_at == (100 if shift_run_at else 90)
    assert t.next_at == 116 and t._visual_rewind_at == 110 and t._preparation_at == 112
    resumed = t.position(111, phrase_length=8, bpm=60, running=False,
                         pending_auto_result=False)
    # Pause freezes velocity, not the recoverable position or destination.
    # Resuming restores the same backward motion from exactly that position.
    assert frozen == (10.5, 0.0, 6)
    assert resumed[0] == frozen[0] and resumed[2] == frozen[2]
    assert resumed[1] < 0.0
    assert t.pending_rewind == 2 and t.visual_offset_beats == 8
    assert not t.paused and t.paused_at == 0


def test_resume_keeps_inactive_clock_sentinels_and_source_position_unchanged():
    t = VisualTransport(run_at=90, play_from_beat=3)
    t.pause(at=100)
    t.resume(now=110, shift_run_at=False)
    assert t.run_at == 90 and t.play_from_beat == 3
    assert t.next_at == t._visual_rewind_at == t._preparation_at == 0
    assert not t.paused and t.paused_at == 0


def test_transport_engine_alias_has_exactly_one_state_owner(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        assert engine.run_at == engine.visual_transport.run_at
        engine.run_at = 123.5
        engine._preview_loop_pending = True
        engine.visual_gap_beats = 7
        assert engine.visual_transport.run_at == 123.5
        assert engine.visual_transport._preview_loop_pending
        assert engine.visual_transport.visual_gap_beats == 7
        engine.visual_transport.pending_rewind = 2.0
        assert engine.pending_rewind == 2.0
        engine._stop()
        assert engine.run_at == 123.5  # stopping does not alter historical origin
        assert engine.pending_rewind is None
        assert engine.visual_gap_beats == 7
    finally:
        engine.db.close()


def test_retry_epochs_are_absolute_and_shift_together_on_resume():
    t = VisualTransport(visual_offset_beats=8)
    t.schedule_preparation({"duration_beats": 4}, source_from_beat=2,
                           from_visual=15, now=100, reverse_seconds=2, bpm=60)
    schedule = t.preparation_schedule()
    assert schedule == {
        "reverse_at_ms": 100000.0,
        "prepare_at_ms": 102000.0,
        "deadline_at_ms": 106000.0,
        "from_beat": 15,
        "to_beat": 6,
    }
    t.pause(at=101)
    t.resume(now=111, shift_run_at=False)
    after = t.preparation_schedule()
    assert after["reverse_at_ms"] == pytest.approx(110000)
    assert after["prepare_at_ms"] == pytest.approx(112000)
    assert after["deadline_at_ms"] == pytest.approx(116000)
    assert after["from_beat"] == schedule["from_beat"]
    assert after["to_beat"] == schedule["to_beat"]
    t.begin_take(loop_continuation=True)
    assert t.preparation_schedule() is None

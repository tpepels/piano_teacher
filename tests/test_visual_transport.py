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

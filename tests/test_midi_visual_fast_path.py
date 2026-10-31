"""Physical MIDI callbacks feed the native in-memory event ring."""
from __future__ import annotations

import time
from types import SimpleNamespace

from piano_teacher.live_event_ring import LiveEventRing
from piano_teacher.runtime_timings import RuntimeTimings
from piano_teacher.server import PracticeEngine
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece


def test_ring_is_bounded_and_monotonically_queryable():
    ring = LiveEventRing(capacity=4)
    for n in range(8):
        ring.publish({"sequence": n, "transport_id": 3, "status": "on_time"})
    assert [e["sequence"] for e in ring.after(4)] == [5, 6, 7]
    assert ring.after(7) == []


def test_cpu_diagnostics_are_bounded_and_display_p95():
    timings = RuntimeTimings()
    for n in range(400):
        timings.midi_ms.append(float(n % 16))
        timings.state_ms.append(float(n % 12))
    result = timings.snapshot()
    assert result["midi_callback"]["samples"] == 256
    assert result["full_state"]["samples"] == 128
    assert result["midi_callback"]["p95_ms"] >= result["midi_callback"]["median_ms"]
    assert result["multiprocessing"] is False


def test_note_on_publishes_to_memory_without_waiting_for_release(tmp_path):
    notes = (Note(0, .7, 60, 0, 0, "right", "first"),)
    piece = Piece("Callback", 80, notes,
                  (Phrase(1, 1, 1, 0, 4, notes),), bar_boundaries=(0, 4))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(piece, exercise_strategy="legacy")
        engine.midi.port = SimpleNamespace(closed=False)
        engine.start()
        engine.run_at = time.monotonic() - .015
        engine._receive(SimpleNamespace(type="note_on", note=60,
                                        velocity=85, channel=0))
        events = engine.live_events.after(0)
        assert events and events[-1]["status"] == "on_time"
        assert events[-1]["source_id"] == "first"
        assert engine.recorder.presses[-1].release is None
        assert engine.performance_diagnostics()["midi_callback"]["samples"] == 1
    finally:
        engine.db.close()

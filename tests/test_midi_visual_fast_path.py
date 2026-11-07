"""Physical MIDI callbacks feed the native in-memory event ring."""
from __future__ import annotations

import time

import pytest
from types import SimpleNamespace

from piano_teacher.feedback_events import FeedbackEventLog
from piano_teacher.runtime_timings import RuntimeTimings
from piano_teacher.server import PracticeEngine
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece


TAKE = {"piece_fingerprint": "f", "revision": 1, "transport_id": 3,
        "mode": "practice", "graded": True}


def test_log_retains_until_acknowledged_and_reports_overflow():
    log = FeedbackEventLog(capacity=4)
    for _ in range(3):
        log.publish({"kind": "attack", **TAKE, "status": "on_time"})
    # Reading without acknowledging never loses an event.
    assert [e["sequence"] for e in log.after(0)["events"]] == [1, 2, 3]
    assert [e["sequence"] for e in log.after(0)["events"]] == [1, 2, 3]
    assert [e["sequence"] for e in log.after(2)["events"]] == [3]
    assert log.after(3)["events"] == []
    for _ in range(6):
        log.publish({"kind": "attack", **TAKE, "status": "on_time"})
    reply = log.after(3)
    assert [e["sequence"] for e in reply["events"]] == [6, 7, 8, 9]
    assert reply["lost_through"] == 5  # overflow is reported, never hidden


def test_log_rejects_events_without_take_identity():
    log = FeedbackEventLog()
    with pytest.raises(ValueError):
        log.publish({"kind": "attack", "transport_id": 3})
    with pytest.raises(ValueError):
        log.publish({"kind": "glow", **TAKE})


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
        engine.plan = LearningPlan(piece, exercise_strategy="source-progression")
        engine.fingerprint = "midi-callback-fixture"
        engine.midi.port = SimpleNamespace(closed=False)
        engine.start()
        engine.visual_transport.run_at = time.monotonic() - .015
        engine._receive(SimpleNamespace(type="note_on", note=60,
                                        velocity=85, channel=0))
        events = engine.feedback_events.after(0)["events"]
        assert events and events[-1]["kind"] == "attack"
        assert events[-1]["status"] == "on_time"
        assert events[-1]["transport_id"] == engine.transport_id
        assert events[-1]["revision"] == engine.score_revision
        assert events[-1]["graded"] is True
        assert events[-1]["source_id"] == "first"
        assert engine.recorder.presses[-1].release is None
        assert engine.performance_diagnostics()["midi_callback"]["samples"] == 1
    finally:
        engine.db.close()

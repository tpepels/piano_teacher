"""Low-overhead live feedback delivery and local-processing diagnostics."""
from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import pytest

from piano_teacher.midi_visual_publisher import MidiVisualPublisher
from piano_teacher.runtime_timings import RuntimeTimings
from piano_teacher.server import PracticeEngine
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece


def test_live_udp_is_loopback_only_and_best_effort():
    sender = MidiVisualPublisher()
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(.25)
    try:
        with pytest.raises(ValueError):
            sender.subscribe(80)
        sender.subscribe(receiver.getsockname()[1])
        sender.publish({"sequence": 3, "transport_id": 8, "status": "on_time",
                        "pitch": 60, "source_id": "midi-first"})
        payload, origin = receiver.recvfrom(2048)
        decoded = json.loads(payload)
        assert origin[0] == "127.0.0.1"
        assert decoded["status"] == "on_time" and decoded["source_id"] == "midi-first"
        assert decoded["transport_id"] == 8
        assert "grade" not in decoded
        sender.publish({"sequence": 4, "status": "count_in"})
        with pytest.raises(socket.timeout):
            receiver.recvfrom(2048)
    finally:
        sender.close()
        receiver.close()


def test_unsubscribed_publisher_never_sends_a_packet():
    sender = MidiVisualPublisher()
    try:
        sender.publish({"status": "on_time", "sequence": 1})
        assert sender.port == 0
    finally:
        sender.close()


def test_perf_stats_are_bounded_and_display_p95():
    samples = RuntimeTimings()
    for number in range(400):
        samples.midi_ms.append(float(number % 16))
        samples.state_ms.append(float(number % 12))
    report = samples.snapshot()
    assert report["midi_callback"]["samples"] == 256
    assert report["full_state"]["samples"] == 128
    assert report["midi_callback"]["p95_ms"] >= report["midi_callback"]["median_ms"]
    assert report["multiprocessing"] is False


def test_midi_callback_pushes_provisional_green_without_waiting_for_release(tmp_path):
    notes = (Note(0, .7, 60, 0, 0, "right", "first"),)
    piece = Piece("Callback", 80, notes,
                  (Phrase(1, 1, 1, 0, 4, notes),),
                  bar_boundaries=(0, 4))
    app = PracticeEngine(tmp_path, enable_midi=False)
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(.3)
    try:
        app.plan = LearningPlan(piece, exercise_strategy="legacy")
        app.midi.port = SimpleNamespace(closed=False)
        app.subscribe_midi_visual(receiver.getsockname()[1])
        app.start()
        import time
        app.run_at = time.monotonic() - .015
        app._receive(SimpleNamespace(type="note_on", note=60,
                                     velocity=85, channel=0))
        packet = json.loads(receiver.recvfrom(2048)[0])
        assert packet["status"] == "on_time"
        assert packet["source_id"] == "first"
        assert app.recorder.presses[-1].release is None
        assert app.performance_diagnostics()["midi_callback"]["samples"] == 1
        app.state()
        assert app.performance_diagnostics()["full_state"]["samples"] == 1
    finally:
        receiver.close()
        app.midi_visual_publisher.close()
        app.db.close()

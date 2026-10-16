"""USB MIDI discovery cancels interrupted attempts and retains reconnect intent."""
import sys

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


class InputPort:
    def __init__(self, *, close_error=False):
        self.closed = False
        self.close_error = close_error
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        if self.close_error:
            raise OSError("USB device is already gone")
        self.closed = True


class MidiBackend:
    def __init__(self):
        self.names = ["USB Piano"]
        self.discovery_error = None
        self.open_error = None
        self.opened = []
        self.attempts = []

    def get_input_names(self):
        if self.discovery_error:
            raise self.discovery_error
        return list(self.names)

    def open_input(self, name, *, callback):
        self.attempts.append(name)
        if self.open_error:
            raise self.open_error
        if name not in self.names:
            raise OSError("Unknown MIDI input")
        port = InputPort()
        self.opened.append(port)
        return port


@pytest.fixture
def connected(tmp_path, monkeypatch):
    midi = MidiBackend()
    monkeypatch.setitem(sys.modules, "mido", midi)
    engine = PracticeEngine(tmp_path)
    notes = (Note(0, 1, 60, 0, 0, "right"),)
    engine.plan = LearningPlan(Piece("Reconnect", 100, notes, (Phrase(1, 1, 2, 0, 8, notes),)))
    engine.connect("USB Piano")
    yield engine, midi
    if engine.midi_port is not None:
        engine.midi_port.close_error = False
        engine.midi_port.close()
    engine.db.close()


def test_unplug_stops_attempt_and_retains_saved_device_for_replug(connected):
    engine, midi = connected
    old_port = engine.midi_port
    engine.start()
    assert not engine.preview_only
    midi.names = []

    assert engine.ports() == []

    assert engine.midi_port is None and engine.midi_device == ""
    assert old_port.closed
    assert not engine.running and engine.recorder is None
    assert not engine.auto and engine.next_at == 0
    assert "disconnected" in engine.feedback.lower()
    assert "USB Piano" in engine.feedback
    assert engine.preferences()["midi_device"] == "USB Piano"
    assert not engine.plan.mastered and engine.plan.streak == 0
    midi.names = ["USB Piano"]
    assert engine.ports() == ["USB Piano"]
    engine.connect(engine.preferences()["midi_device"])
    assert engine.midi_device == "USB Piano"
    assert engine.midi_port is not old_port and not engine.midi_port.closed
    engine.start()
    assert not engine.preview_only


def test_closed_port_is_detected_even_when_name_is_still_enumerated(connected):
    engine, _ = connected
    engine.start()
    engine.midi_port.closed = True

    assert engine.ports() == ["USB Piano"]

    assert engine.midi_device == "" and engine.midi_port is None
    assert not engine.running
    assert engine.preferences()["midi_device"] == "USB Piano"


def test_unplug_during_clean_feedback_discards_pending_mastery(connected):
    from types import SimpleNamespace

    engine, midi = connected
    engine.plan.bpm = engine.plan.target_bpm
    engine.plan.streak = 2
    engine.start()
    engine.running = False
    engine.pending_result = SimpleNamespace(correct=1, notes=[object()], extra_notes=0)
    engine.next_at = 1.0
    midi.names = []

    engine.ports()

    assert engine.pending_result is None
    assert engine.state()["phase"] == "ready"
    assert not engine.plan.mastered


def test_failed_reconnect_clears_selection_without_forgetting_preferred_device(connected):
    engine, midi = connected
    old_port = engine.midi_port
    engine.start()
    midi.open_error = OSError("Access denied")

    with pytest.raises(RuntimeError, match="Cannot connect.*Access denied"):
        engine.connect("Other Piano")

    assert old_port.closed
    assert engine.midi_port is None and engine.midi_device == ""
    assert not engine.running and not engine.auto
    assert engine.preferences()["midi_device"] == "USB Piano"


def test_close_failure_does_not_prevent_reconnecting_or_unplug_cleanup(connected):
    engine, midi = connected
    old_port = engine.midi_port
    old_port.close_error = True

    engine.connect("USB Piano")

    assert old_port.close_calls == 1
    assert engine.midi_port is not old_port
    assert engine.midi_device == "USB Piano"
    engine.midi_port.close_error = True
    engine.start()
    midi.names = []
    assert engine.ports() == []
    assert engine.midi_port is None and engine.midi_device == ""
    assert not engine.running


def test_discovery_failure_is_actionable_and_keeps_a_healthy_connection(connected):
    engine, midi = connected
    port = engine.midi_port
    midi.discovery_error = OSError("ALSA is unavailable")

    with pytest.raises(RuntimeError, match="Cannot list MIDI.*ALSA is unavailable"):
        engine.ports()

    assert "ALSA is unavailable" in engine.feedback
    assert engine.midi_port is port and not port.closed
    assert engine.midi_device == "USB Piano"


def test_closed_port_stops_attempt_even_when_device_discovery_fails(connected):
    engine, midi = connected
    engine.start()
    engine.midi_port.closed = True
    midi.discovery_error = OSError("ALSA is unavailable")

    with pytest.raises(RuntimeError, match="Cannot list MIDI"):
        engine.ports()

    assert engine.midi_port is None and engine.midi_device == ""
    assert not engine.running
    assert engine.preferences()["midi_device"] == "USB Piano"


def test_explicit_disconnect_clears_saved_preference_despite_close_failure(connected):
    engine, _ = connected
    engine.midi_port.close_error = True
    engine.start()

    engine.connect("")

    assert engine.midi_port is None and engine.midi_device == ""
    assert engine.preferences()["midi_device"] == ""
    assert not engine.running


def test_previously_selected_piano_auto_connects_without_restarting_practice(
        tmp_path, monkeypatch):
    midi = MidiBackend()
    monkeypatch.setitem(sys.modules, "mido", midi)
    first = PracticeEngine(tmp_path)
    try:
        first.connect("USB Piano")
        first.connect("USB Piano")
        preferred = first.preferences()["midi_device"]
    finally:
        first.midi_port.close()
        first.db.close()
    second = PracticeEngine(tmp_path)
    try:
        assert preferred == "USB Piano"
        assert second.midi_device == ""
        state = second.state()  # first poll should offer bounded discovery
        assert state["device"] == "USB Piano"
        assert second.midi_port is not None
        assert not second.running
        assert second.recorder is None
        assert not second.preview_only
        assert second.transport_id == 0
    finally:
        if second.midi_port:
            second.midi_port.close()
        second.db.close()


def test_auto_reconnect_after_usb_return_never_resumes_cancelled_take(
        connected, monkeypatch):
    engine, midi = connected
    from piano_teacher import server
    clock = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    engine.start()
    transport_before = engine.transport_id
    assert engine.running
    original = engine.midi_port
    midi.names = []
    assert engine.ports() == []
    assert original.closed
    assert not engine.running and engine.recorder is None
    assert engine.preferences()["midi_device"] == "USB Piano"
    assert not engine.auto

    midi.names = ["Other Device"]
    clock[0] = 105.0
    assert engine.ports() == ["Other Device"]
    assert engine.midi_port is None  # no substitution with another piano
    midi.names = ["Other Device", "USB Piano"]
    clock[0] = 107.0
    assert engine.ports() == midi.names
    assert engine.midi_device == "USB Piano"
    assert engine.midi_port is not original
    assert not engine.running and engine.recorder is None
    assert engine.transport_id == transport_before
    assert not engine.plan.mastered
    assert "Press Start" in engine.feedback
    engine.start()
    assert engine.running and not engine.preview_only


def test_auto_reconnect_rate_limits_failed_alsa_open_and_recovers(
        connected, monkeypatch):
    engine, midi = connected
    from piano_teacher import server
    clock = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    midi.names = []
    engine.ports()
    attempts_before = len(midi.attempts)
    midi.names = ["USB Piano"]
    midi.open_error = OSError("Device still busy")
    clock[0] = 105.0
    for _ in range(5):
        assert engine.ports() == ["USB Piano"]
    assert len(midi.attempts) == attempts_before + 1
    assert "Cannot reconnect" in engine.feedback
    midi.open_error = None
    clock[0] = 108.0
    engine.ports()
    assert len(midi.attempts) == attempts_before + 1
    assert engine.midi_port is None
    clock[0] = 109.1
    engine.ports()
    assert engine.midi_device == "USB Piano"
    assert engine.midi_port is not None


def test_automatic_discovery_detects_disappearance_without_open_input_closing(
        connected, monkeypatch):
    engine, midi = connected
    from piano_teacher import server
    clock = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    engine.start()
    original = engine.midi_port
    midi.names = []
    engine._midi_next_scan_at = 0.0
    clock[0] = 105.0
    state = engine.state()
    assert state["device"] == ""
    assert original.closed
    assert not engine.running
    assert "disconnected" in engine.feedback.lower()


def test_explicit_disconnect_never_auto_connects_even_when_port_available(connected):
    engine, midi = connected
    engine.connect("")
    assert engine.preferences()["midi_device"] == ""
    before = len(midi.attempts)
    for _ in range(4):
        engine.ports()
        engine.state()
    assert engine.midi_port is None
    assert len(midi.attempts) == before

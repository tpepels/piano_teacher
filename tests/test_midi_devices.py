"""Software device-loss and calibration reactions, without attached hardware."""
import mido
import pytest

from piano_teacher import sample_piano
from piano_teacher.inprocess import EngineCommands, INVALID
from piano_teacher.library import ScoreLibrary
from piano_teacher.midi_calibration import MidiTapCalibration
from piano_teacher.server import PracticeEngine


class InputPort:
    def __init__(self, callback):
        self.callback = callback
        self.closed = False
        self.close_error = False

    def close(self):
        self.closed = True
        if self.close_error:
            raise OSError("device already unplugged")

    def press(self, pitch=60):
        self.callback(mido.Message("note_on", note=pitch, velocity=80))

    def release(self, pitch=60):
        self.callback(mido.Message("note_off", note=pitch))


class Backend:
    def __init__(self):
        self.names = ["USB Piano"]
        self.open_error = None
        self.scan_error = None
        self.attempts = []
        self.ports = []

    def get_input_names(self):
        if self.scan_error:
            raise self.scan_error
        return list(self.names)

    def open_input(self, name, *, callback):
        self.attempts.append(name)
        if self.open_error:
            raise self.open_error
        port = InputPort(callback)
        self.ports.append(port)
        return port


@pytest.fixture
def connected(tmp_path, monkeypatch):
    backend = Backend()
    monkeypatch.setattr(mido, "open_input", backend.open_input)
    monkeypatch.setattr(mido, "get_input_names", backend.get_input_names)
    monkeypatch.delenv("PIANO_TEACHER_SOUNDFONT", raising=False)
    monkeypatch.setattr(sample_piano, "DEFAULT_SOUNDFONT", tmp_path / "absent.sf2")
    now = [100.0]
    engine = PracticeEngine(tmp_path / "app", clock=lambda: now[0])
    midi = mido.MidiFile()
    midi.tracks.append(mido.MidiTrack([
        mido.Message("note_on", note=60, velocity=80),
        mido.Message("note_off", note=60, time=480),
    ]))
    path = tmp_path / "device.mid"
    midi.save(path)
    try:
        engine.load(str(path))
        engine.connect("USB Piano")
        yield engine, backend, now
    finally:
        if engine.listen.thread is not None:
            engine.listen.thread.join(timeout=10)
            assert not engine.listen.thread.is_alive()
        engine.close()


def test_unplug_cancels_take_and_reconnect_requires_a_fresh_start(connected):
    engine, backend, now = connected
    engine.start()
    assert engine.state()["running"]
    old = backend.ports[-1]
    old.press()
    backend.names = []
    assert engine.ports() == []
    assert old.closed and not engine.state()["running"]
    assert engine.preferences()["midi_device"] == "USB Piano"
    assert "disconnected" in engine.state()["feedback"].lower()
    backend.names = ["Other Piano"]
    now[0] += 5
    engine.ports()
    assert engine.state()["device"] == ""
    backend.names.append("USB Piano")
    engine.ports()
    state = engine.state()
    assert state["device"] == "USB Piano" and not state["running"]
    assert state["midi_held_pitches"] == []
    assert not state["mastered"]
    assert backend.attempts == ["USB Piano", "USB Piano"]
    engine.start()
    assert engine.state()["running"]
    # A physical key held on the lost device supplies no new attack.
    attacks = engine.state()["midi_input_count"]
    backend.ports[-1].release()
    assert engine.state()["midi_input_count"] == attacks
    assert not engine.state()["mastered"]
    backend.ports[-1].press()
    assert engine.state()["midi_input_note"] == 60
    assert engine.state()["midi_input_count"] == attacks + 1


def test_failed_reconnect_is_bounded_then_recovers_without_resuming(connected):
    engine, backend, now = connected
    backend.names = []
    engine.ports()
    backend.names = ["USB Piano"]
    backend.open_error = OSError("device busy")
    now[0] += 5
    for _ in range(3):
        engine.ports()
    assert len(backend.attempts) == 2
    assert "device busy" in engine.state()["feedback"]
    backend.open_error = None
    now[0] += 3
    engine.ports()
    assert len(backend.attempts) == 2
    now[0] += 2
    engine.ports()
    assert engine.state()["device"] == "USB Piano"
    assert not engine.state()["running"]


def test_discovery_failure_keeps_healthy_device_but_closed_port_cancels(connected):
    engine, backend, _ = connected
    engine.start()
    backend.scan_error = OSError("ALSA unavailable")
    with pytest.raises(RuntimeError, match="ALSA unavailable"):
        engine.ports()
    assert not backend.ports[-1].closed
    assert engine.state()["device"] == "USB Piano"
    backend.ports[-1].closed = True
    with pytest.raises(RuntimeError, match="Cannot list MIDI"):
        engine.ports()
    assert not engine.state()["running"]
    assert engine.preferences()["midi_device"] == "USB Piano"


def test_invalid_selection_preserves_take_and_explicit_disconnect_forgets_device(connected):
    engine, backend, now = connected
    engine.start()
    before = engine.state()
    status, _ = EngineCommands(engine=engine).request("midi.device.select", '{"name":42}')
    assert status == INVALID
    assert not backend.ports[-1].closed
    assert engine.state()["running"]
    assert engine.state()["transport_id"] == before["transport_id"]
    backend.ports[-1].close_error = True
    engine.connect("")
    assert not engine.state()["running"]
    assert engine.preferences()["midi_device"] == ""
    attempts = len(backend.attempts)
    now[0] += 20
    engine.ports()
    engine.state()
    assert len(backend.attempts) == attempts


def test_calibration_collects_real_ingress_then_applies_persists_and_resets(connected, tmp_path):
    engine, backend, now = connected
    engine.control("calibration_start")
    # The published epoch drives an external musician's taps, not a second clock policy.
    calibration = engine.state()["midi_calibration"]
    epoch = calibration["start_at_ms"] / 1000
    period = 60 / calibration["bpm"]
    with pytest.raises(ValueError, match="Finish"):
        engine.control("calibration_apply")
    for beat in range(4, 44):
        now[0] = epoch + beat * period + .08
        backend.ports[-1].press()
        backend.ports[-1].release()
    now[0] = epoch + 44 * period + .1
    result = engine.state()["midi_calibration"]["result"]
    assert result["reliable"] and result["samples"] == 40
    assert engine.preferences()["midi_offset_ms"] == 0
    engine.control("calibration_apply")
    assert engine.preferences()["midi_offset_ms"] == pytest.approx(80, abs=1)
    assert ScoreLibrary(tmp_path / "app" / "config").public_settings()["midi_offset_ms"] == 80
    engine.start()
    deadline = engine.state()["visual_run_at_ms"] / 1000
    now[0] = deadline + .08
    backend.ports[-1].press()
    events = engine.feedback_events.after(0)["events"]
    attack = next(event for event in reversed(events) if event["kind"] == "attack")
    assert attack["status"] == "on_time"
    assert attack["played_source_beat"] == pytest.approx(0, abs=.001)
    assert attack["received_at"] == pytest.approx(deadline, abs=.001)
    backend.ports[-1].release()
    engine.control("calibration_start")
    engine.control("calibration_cancel")
    assert engine.preferences()["midi_offset_ms"] == 80
    engine.control("calibration_reset")
    assert engine.preferences()["midi_offset_ms"] == 0


@pytest.mark.parametrize("offsets,reliable", [((.08, .08, .18, .08, .08), True),
                                             ((.08, .08, .18, .19, .08), False)])
def test_calibration_excludes_one_outlying_round_but_rejects_disagreement(offsets, reliable):
    calibration = MidiTapCalibration()
    calibration.start(100)
    for round_index, offset in enumerate(offsets):
        first = calibration.start_at + (4 + round_index * 8) * calibration.period
        for tap in range(8):
            assert calibration.observe(first + tap * calibration.period + offset)
    result = calibration.snapshot(calibration.start_at + 44 * calibration.period + .1)["result"]
    assert result["reliable"] is reliable
    if reliable:
        assert result["estimate_ms"] == pytest.approx(80, abs=1)
    else:
        assert result["error"]

"""Hardware lifetime and retry policy run without a practice engine."""
from types import SimpleNamespace

import pytest

from piano_teacher.application import midi_connection

class Port:
    def __init__(self, events, *, fail_close=False):
        self.closed = False
        self.events = events
        self.fail_close = fail_close

    def close(self):
        self.events.append("close")
        if self.fail_close:
            raise OSError("already unplugged")
        self.closed = True


class Backend:
    def __init__(self):
        self.names = ["Chosen piano", "Other piano"]
        self.events = []
        self.callbacks = []
        self.open_error = None
        self.scan_error = None

    def get_input_names(self):
        self.events.append("scan")
        if self.scan_error:
            raise self.scan_error
        return self.names

    def open_input(self, name, *, callback):
        self.events.append(("open", name))
        if self.open_error:
            raise self.open_error
        self.callbacks.append(callback)
        return Port(self.events)


def owner(monkeypatch, *, enabled=True):
    clock = [100.0]
    monkeypatch.setattr(midi_connection.time, "monotonic", lambda: clock[0])
    backend = Backend()
    return midi_connection.MidiConnection(enabled=enabled, backend=backend), backend, clock


def test_selection_releases_before_cancellation_and_closes_before_open(monkeypatch):
    device, backend, clock = owner(monkeypatch)
    previous = Port(backend.events)
    device.port, device.device = previous, "Previous piano"
    device.input_note, device.input_at, device.input_count = 60, 99.0, 7
    device.probe.start("Previous piano", now=99)
    heard = []
    with device.selecting("Chosen piano", callback=heard.append) as selection:
        assert device.port is None and device.device == ""
        assert device.input_note is None and device.input_at is None
        assert not device.probe.active and not previous.closed
        backend.events.append("cancel attempt")
    assert backend.events == ["cancel attempt", "close", ("open", "Chosen piano")]
    assert device.connected and device.device == "Chosen piano"
    assert device.input_count == 7 and device.next_scan_at == 103
    assert selection.notice.connected is True and selection.notice.next_action == "Press Start when you are ready."
    message = SimpleNamespace(type="note_on", note=64, velocity=80)
    backend.callbacks[0](message)
    assert heard == [message]  # Forward the original hardware callback, without a timing wrapper.


def test_loss_finishes_cancellation_before_close_and_delays_only_saved_reconnect(monkeypatch):
    device, backend, clock = owner(monkeypatch)
    previous = Port(backend.events)
    device.port, device.device = previous, "Chosen piano"
    with device.disconnected() as notice:
        assert device.port is None and not previous.closed
        backend.events.append("cancel attempt")
    assert backend.events == ["cancel attempt", "close"]
    assert "Chosen piano" in notice.feedback and device.retry_after == 104
    assert device.restore_preferred(("Other piano",), "Chosen piano", callback=lambda _: None) is None
    assert device.restore_preferred(tuple(backend.names), "Chosen piano", callback=lambda _: None) is None
    clock[0] = 104
    restored = device.restore_preferred(tuple(backend.names), "Chosen piano", callback=lambda _: None)
    assert restored.connected is True and restored.sampled_at == 104
    assert device.device == "Chosen piano" and device.port is not previous
    assert backend.events[-1] == ("open", "Chosen piano")


def test_failed_saved_reconnect_is_bounded_and_cannot_select_another_device(monkeypatch):
    device, backend, clock = owner(monkeypatch)
    backend.open_error = OSError("device busy")
    notice = device.restore_preferred(tuple(backend.names), "Chosen piano", callback=lambda _: None)
    assert "Cannot reconnect" in notice.feedback and "device busy" in notice.feedback
    assert notice.connected is None and device.retry_after == 104
    for instant in (100, 101, 103.999):
        clock[0] = instant
        assert device.restore_preferred(tuple(backend.names), "Chosen piano", callback=lambda _: None) is None
    assert backend.events == [("open", "Chosen piano")]
    backend.open_error = None
    clock[0] = 104
    device.restore_preferred(tuple(backend.names), "Chosen piano", callback=lambda _: None)
    assert backend.events == [("open", "Chosen piano"), ("open", "Chosen piano")]


@pytest.mark.parametrize("closed", (False, True))
def test_discovery_failure_reports_health_without_destroying_the_connection(monkeypatch, closed):
    device, backend, clock = owner(monkeypatch)
    previous = Port(backend.events)
    previous.closed = closed
    device.port, device.device = previous, "Chosen piano"
    backend.scan_error = OSError("ALSA unavailable")
    scan = device.scan()
    assert scan.error is backend.scan_error and scan.lost is closed
    assert device.port is previous and device.device == "Chosen piano"
    assert "Cannot list MIDI" in scan.feedback and "ALSA unavailable" in scan.feedback


def test_poll_schedule_does_not_scan_or_reconnect_without_explicit_preference(monkeypatch):
    device, backend, clock = owner(monkeypatch)
    assert not device.scan_due("") and backend.events == []
    assert device.scan_due("Chosen piano") and device.next_scan_at == 103
    assert not device.scan_due("Chosen piano")
    clock[0] = 102.999
    assert not device.scan_due("Chosen piano")
    clock[0] = 103
    assert device.scan_due("Chosen piano")
    assert backend.events == []  # Scheduling is independent of the ALSA request.


@pytest.mark.parametrize("name,message", [(None, "must be text"), (42, "must be text"),
                                          ("Chosen piano", "MIDI input is disabled")])
def test_invalid_selection_still_releases_old_device_before_validation(monkeypatch, name, message):
    device, backend, clock = owner(monkeypatch, enabled=False)
    previous = Port(backend.events, fail_close=True)
    device.port, device.device = previous, "Previous piano"
    with pytest.raises(ValueError, match=message):
        with device.selecting(name, callback=lambda _: None):
            backend.events.append("cancel attempt")
    assert backend.events == ["cancel attempt", "close"]
    assert device.port is None and device.device == ""
    assert device.next_scan_at == 103 and device.retry_after == 0
    assert not device.scan_due("Previous piano")
    assert device.scan().names == ()


def test_failed_explicit_open_leaves_no_port_and_exposes_the_backend_reason(monkeypatch):
    device, backend, clock = owner(monkeypatch)
    backend.open_error = OSError("access denied")
    with pytest.raises(RuntimeError, match="Cannot connect.*access denied"):
        with device.selecting("Chosen piano", callback=lambda _: None):
            pass
    assert device.port is None and device.device == "" and not device.connected


def test_hardware_observation_preserves_callback_time_without_implying_assessment(monkeypatch):
    device, backend, clock = owner(monkeypatch)
    device.port, device.device = Port(backend.events), "Chosen piano"
    device.diagnostics_action("start", running=False)
    clock[0] = 500
    device.observe(SimpleNamespace(type="note_on", note=64, velocity=90, channel=0), now=100.25)
    assert device.input_count == 1 and device.input_note == 64 and device.input_at == 100.25
    assert device.probe.events[-1]["at_s"] == .25
    device.observe(SimpleNamespace(type="note_on", note=64, velocity=0, channel=0), now=100.5)
    assert device.input_count == 1
    with pytest.raises(RuntimeError, match="Stop the current"):
        device.diagnostics_action("start", running=True)
    stopped = device.diagnostics_action("stop", running=False)
    assert stopped["note_ons"] == 1 and stopped["note_offs"] == 1


def test_retry_and_scan_deadlines_are_sampled_after_the_old_port_finishes_closing(monkeypatch):
    device, backend, clock = owner(monkeypatch)

    class SlowClose(Port):
        def close(self):
            super().close()
            clock[0] += .5

    device.port, device.device = SlowClose(backend.events), "Chosen piano"
    with device.disconnected():
        pass
    assert device.retry_after == 104.5
    device.port, device.device = SlowClose(backend.events), "Chosen piano"
    with device.selecting("", callback=lambda _: None):
        pass
    assert device.next_scan_at == 104 and device.retry_after == 0

"""Hardware acceptance can be tested against callback fixtures without a USB piano."""
from types import SimpleNamespace

import pytest

from piano_teacher.hardware_probe import HardwareProbe, MAX_EVENTS
from piano_teacher.server import PracticeEngine


def midi(kind: str, **attrs):
    return SimpleNamespace(type=kind, **attrs)


def test_opt_in_probe_records_chords_velocity_release_and_sustain_without_scoring():
    probe = HardwareProbe()
    assert not probe.snapshot(now=100)["active"]
    probe.receive(midi("note_on", note=60, velocity=70), now=100)
    probe.start("Kawai CA", now=100)
    probe.receive(midi("note_on", note=60, velocity=25, channel=0), now=100.10)
    probe.receive(midi("note_on", note=64, velocity=110, channel=0), now=100.13)
    probe.receive(midi("note_on", note=67, velocity=75, channel=0), now=100.16)
    probe.receive(midi("control_change", control=64, value=127, channel=0), now=100.20)
    probe.receive(midi("note_on", note=60, velocity=0, channel=0), now=100.40)
    probe.receive(midi("note_off", note=64, velocity=33, channel=0), now=100.41)
    probe.receive(midi("note_off", note=67, velocity=0, channel=0), now=100.43)
    probe.receive(midi("control_change", control=64, value=0, channel=0), now=100.45)
    result = probe.stop(now=101)
    assert result["duration_s"] == 1.0
    assert (result["note_ons"], result["note_offs"], result["chord_pairs"]) == (3, 3, 2)
    assert (result["velocity_min"], result["velocity_max"]) == (25, 110)
    assert result["pedal_changes"] == 2
    assert not result["sustain_down"] and not result["held_notes"]
    assert not result["orphan_releases"] and not result["repeated_attacks"]
    assert [event["type"] for event in result["events"]] == [
        "note_on", "note_on", "note_on", "sustain_down", "note_off",
        "note_off", "note_off", "sustain_up",
    ]
    probe.receive(midi("note_on", note=99, velocity=80), now=102)
    assert probe.snapshot(now=102) == result


def test_missing_release_duplicate_notes_timeout_and_bounded_storage():
    probe = HardwareProbe()
    probe.start("USB Piano", now=1)
    probe.receive(midi("note_off", note=60, velocity=0), now=1.05)
    probe.receive(midi("note_on", note=60, velocity=65), now=1.10)
    probe.receive(midi("note_on", note=60, velocity=70), now=1.12)
    for index in range(MAX_EVENTS + 25):
        probe.receive(midi("note_on", note=(index % 60) + 60, velocity=30), now=1.3 + index / 1000)
    snap = probe.snapshot(now=2)
    assert snap["orphan_releases"] == 1 and snap["repeated_attacks"] >= 1
    assert snap["stored_events"] == MAX_EVENTS and snap["dropped_events"] >= 25
    assert snap["held_notes"]
    assert probe.snapshot(now=92)["reason"] == "time_limit"
    assert not probe.active


def test_engine_diagnostics_do_not_interfere_with_existing_practice_or_progress(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        with pytest.raises(RuntimeError, match="Connect"):
            engine.hardware_diagnostics_action("start")
        engine.midi_device = "Kawai"
        engine.midi_port = SimpleNamespace(closed=False)
        engine.hardware_diagnostics_action("start")
        engine._receive(midi("note_on", note=60, velocity=91, channel=0))
        engine._receive(midi("note_off", note=60, velocity=0, channel=0))
        result = engine.hardware_diagnostics_action("stop")
        assert result["note_ons"] == 1 and result["note_offs"] == 1
        assert engine.recorder is None and not engine.running
        assert engine.hardware_diagnostics()["events"] == result["events"]
        assert engine.state()["midi_input_count"] == 1
        with pytest.raises(ValueError, match="start or stop"):
            engine.hardware_diagnostics_action("delete_everything")
        engine.connect("")
        assert not engine.hardware_diagnostics()["active"]
    finally:
        engine.db.close()


def test_running_engine_rejects_probe_start(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.midi_device = "Kawai"
        engine.midi_port = SimpleNamespace(closed=False)
        engine.running = True
        with pytest.raises(RuntimeError, match="Stop the current"):
            engine.hardware_diagnostics_action("start")
    finally:
        engine.db.close()


def test_loopback_diagnostics_api_only_records_when_armed(tmp_path):
    import json
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    from piano_teacher.server import Handler

    engine = PracticeEngine(tmp_path, enable_midi=False)
    class LocalHandler(Handler):
        pass
    LocalHandler.engine = engine
    service = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    thread = Thread(target=service.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{service.server_port}"

    def call(route, data=None):
        body = json.dumps(data).encode() if data is not None else None
        with urlopen(Request(base + route, body, {"Content-Type": "application/json"}
                             if body is not None else {}), timeout=3) as response:
            return json.load(response)
    try:
        assert call("/diagnostics/hardware")["events"] == []
        with pytest.raises(HTTPError) as caught:
            call("/diagnostics/hardware", {"action": "start"})
        assert caught.value.code == 400
        engine.midi_device = "Test MIDI"
        engine.midi_port = SimpleNamespace(closed=False)
        assert call("/diagnostics/hardware", {"action": "start"})["active"]
        engine._receive(midi("note_on", note=72, velocity=100))
        observed = call("/diagnostics/hardware")
        assert observed["device"] == "Test MIDI"
        assert observed["events"][-1]["pitch"] == 72
        assert call("/diagnostics/hardware", {"action": "stop"})["note_ons"] == 1
        engine._receive(midi("note_on", note=74, velocity=100))
        assert call("/diagnostics/hardware")["note_ons"] == 1
        assert "hardware_probe" not in call("/state")
    finally:
        service.shutdown()
        service.server_close()
        thread.join(timeout=3)
        engine.db.close()


def test_cli_reports_without_opening_second_midi_port(tmp_path, monkeypatch, capsys):
    from scripts import check_hardware_session

    from piano_teacher.hardware_probe import HardwareProbe
    probe = HardwareProbe()
    session = {"device": "Kawai CA", "running": False}
    def fake_request(path, data=None):
        if path == "/state":
            return session
        if data and data["action"] == "start":
            return probe.start("Kawai CA", now=100)
        if data and data["action"] == "stop":
            return probe.stop(now=126)
        return probe.snapshot(now=125)
    monkeypatch.setattr(check_hardware_session, "request", fake_request)
    # No real time wait and no piano needed; the CLI accesses the running
    # backend, never opens an additional mido/ALSA input connection.
    monkeypatch.setattr(check_hardware_session.time, "sleep", lambda _: None)
    ticks = iter((0.0, 0.0, 26.0))
    monkeypatch.setattr(check_hardware_session.time, "monotonic",
                        lambda: next(ticks, 26.0))
    report = check_hardware_session.run(25, tmp_path / "midi.json")
    assert report["reason"] == "completed"
    assert (tmp_path / "midi.json").exists()
    assert "Kawai CA" in capsys.readouterr().out

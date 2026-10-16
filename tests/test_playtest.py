"""The playtest entrypoint aggregates live evidence without extra MIDI ports."""
from io import StringIO
import json
from pathlib import Path
import zipfile

import pytest

import playtest


def midi_report():
    return {
        "active": False, "device": "Kawai CA-49", "reason": "completed",
        "note_ons": 12, "note_offs": 11, "pedal_changes": 2,
        "orphan_releases": 0, "repeated_attacks": 1,
        "chord_pairs": 4, "duration_s": 24.0, "stored_events": 28,
        "dropped_events": 0, "held_notes": [{"pitch": 60, "channel": 0}],
        "events": [{"type": "note_on", "pitch": 60,
                    "velocity": 120, "at_s": 1.234}],
    }


def snapshot(*, phase="ready", device="Kawai CA-49", mode="practice",
             input_count=0, transport=2, graded=True, take=None,
             hand="left", running=None):
    return {
        "device": device, "mode": mode, "phase": phase,
        "scoring_available": graded and bool(device),
        "preview_only": not graded, "running": (phase in ("count_in", "playing")
                                            if running is None else running),
        "hand": hand, "streak": 0, "transport_id": transport,
        "midi_input_count": input_count, "take_result": take,
        "bpm": 68, "midi_visual_events": [],
    }


def test_privacy_safe_midi_report_omits_all_raw_notes():
    sanitized = playtest.safe_midi_report(midi_report())
    saved = json.dumps(sanitized)
    assert sanitized["held_note_count"] == 1
    assert "pitch" not in saved
    assert '"velocity":' not in saved
    assert '"velocity_min":' not in saved  # fixture has no aggregate min
    assert "at_s" not in saved
    assert "events" not in sanitized
    assert "held_notes" not in sanitized


def test_one_pass_automatically_arms_idle_midi_probe_then_captures_grading(tmp_path):
    t = [0.]
    calls = []

    def fake_api(path, payload=None):
        calls.append((path, payload))
        if path == "/diagnostics/hardware" and payload == {"action": "start"}:
            return {"active": True}
        if path == "/diagnostics/hardware" and payload == {"action": "stop"}:
            return midi_report()
        if path == "/diagnostics/hardware" and payload is None:
            return midi_report()
        raise AssertionError(path)

    session = playtest.Playtest(tmp_path, request=fake_api, clock=lambda: t[0],
                                midi_seconds=5)
    session.observe(snapshot(input_count=4))
    assert session.probe_started_at == 0.
    assert session.capture is not None
    assert calls[0] == ("/diagnostics/hardware", {"action": "start"})
    assert calls[1] == ("/diagnostics/hardware", None)

    # Polls during the real grading phase never open a MIDI port or send
    # transport actions, and do not restart the diagnostic.
    t[0] = 1.0
    session.observe(snapshot(phase="playing", running=True, input_count=8))
    t[0] = 2.0
    session.observe(snapshot(phase="feedback", input_count=8,
                             take={"clean": True, "correct": 4, "total": 4}))
    t[0] = 5.2
    session.observe(snapshot(phase="ready", input_count=8))
    assert calls.count(("/diagnostics/hardware", {"action": "start"})) == 1
    assert calls.count(("/diagnostics/hardware", {"action": "stop"})) == 1
    assert not any(path in ("/control", "/device") for path, _ in calls)
    assert session.probe_done is True
    assert session.capture.report(6)["clean_takes"] == 1
    assert session.probe_report["held_note_count"] == 1
    assert session.probe_report.get("events") is None
    assert (tmp_path / "midi-summary.json").exists()


def test_short_app_session_keeps_last_probe_snapshot_if_backend_closes(tmp_path):
    calls = []
    t = [2.]

    def api(path, payload=None):
        calls.append((path, payload))
        if path == "/diagnostics/hardware" and payload == {"action": "start"}:
            return {"active": True}
        if path == "/diagnostics/hardware" and payload is None:
            return midi_report()
        raise RuntimeError("backend already stopped")

    session = playtest.Playtest(tmp_path, request=api, clock=lambda: t[0])
    session.observe(snapshot())
    assert session.probe_snapshot is not None
    session._finish_probe()
    assert session.probe_done and session.probe_report is not None
    assert session.probe_report["note_ons"] == 12
    assert '"events":' not in (tmp_path / "midi-summary.json").read_text()


def test_disconnected_preview_never_starts_midi_or_grading(tmp_path):
    calls = []
    session = playtest.Playtest(tmp_path, request=lambda *args:
                                calls.append(args), clock=lambda: 20.0)
    session.observe(snapshot(device="", mode="listen", graded=False))
    session.observe(snapshot(device="", mode="learn", graded=False))
    assert session.capture is None
    assert session.probe_started_at is None
    assert calls == []


def test_hardware_probe_waits_until_idle_and_only_tries_at_bounded_rate(tmp_path):
    calls = []
    t = [2.]

    def temporarily_unavailable(path, payload=None):
        calls.append((path, payload))
        raise RuntimeError("ALSA not ready")

    session = playtest.Playtest(tmp_path, request=temporarily_unavailable,
                                clock=lambda: t[0])
    session.observe(snapshot(phase="playing", running=True))
    assert calls == []  # never starts probe in the middle of a take
    session.observe(snapshot())
    assert len(calls) == 1
    t[0] = 4.
    session.observe(snapshot())
    assert len(calls) == 1
    t[0] = 7.
    session.observe(snapshot())
    assert len(calls) == 2
    assert not any(item[0] in ("/control", "/device") for item in calls)


def test_completed_session_produces_only_one_shareable_zip(tmp_path):
    t = [0.]
    session = playtest.Playtest(tmp_path, midi_seconds=0, clock=lambda: t[0])
    session.capture = playtest.SessionCapture(snapshot(input_count=10))
    session.capture.observe(snapshot(phase="playing", input_count=13))
    session.capture.observe(snapshot(phase="feedback", input_count=13,
        take={"clean": True, "correct": 3, "total": 3}))
    session.probe_report = playtest.safe_midi_report(midi_report())
    (tmp_path / "godot-diagnostics.log").write_text(
        'PHASE8D_FRAME_INTERVALS:{"fps":60,"p95_frame_ms":16.6,'
        '"resident_tile_mib":1.8,"packed_tile_mib":.4}\n'
        'PHASE8B_LISTEN_SOFTWARE_SYNC:{"software_drift_s":-.03,"seeks":0}\n')
    t[0] = 60
    archive = session._finalize()
    assert archive.name == "playtest.zip"
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        assert {"report.md", "report.json", "graded.json", "midi-summary.json",
                "godot-diagnostics.log"} <= names
        assert "godot.log" not in names
        combined = "\n".join(z.read(name).decode() for name in names)
        assert '"pitch"' not in combined
        assert '"velocity": 120' not in combined
        assert '"at_s"' not in combined
        report = json.loads(z.read("report.json"))
        assert report["grading"]["completed_takes"] == 1
        assert report["midi"]["held_notes"] == 1
        assert report["frame_timing"]["median_fps"] == 60
        assert report["listen_software_sync"]["highest_absolute_software_drift_ms"] == 30
        assert report["physical_latency_measured"] is False


def test_session_without_keyboard_produces_honest_incomplete_report(tmp_path):
    (tmp_path / "godot-diagnostics.log").write_text(
        'PHASE8D_FRAME_INTERVALS:{"fps":60,"p95_frame_ms":16.6}\n')
    session = playtest.Playtest(tmp_path, midi_seconds=0)
    archive = session._finalize()
    with zipfile.ZipFile(archive) as z:
        report = json.loads(z.read("report.json"))
        assert report["midi"]["status"] == "missing"
        assert report["grading"]["status"] == "missing"
        assert report["frame_timing"]["status"] == "observed"
        assert report["acceptance"] == "requires_real_hardware_review"


def test_log_draining_preserves_errors_and_filters_aggregate_metrics(tmp_path, capsys):
    stream = StringIO(
        'Godot started\n'
        'PHASE8D_FRAME_INTERVALS:{"fps":60}\n'
        'PHASE8B_LISTEN_SOFTWARE_SYNC:{"software_drift_s":0.01}\n'
        'SCRIPT ERROR: example parse failure\n'
    )
    playtest.record_console(stream, tmp_path / "godot.log",
                            tmp_path / "godot-diagnostics.log")
    assert "Godot started" in (tmp_path / "godot.log").read_text()
    diag = (tmp_path / "godot-diagnostics.log").read_text()
    assert "FRAME_INTERVALS" in diag and "LISTEN_SOFTWARE_SYNC" in diag
    assert "SCRIPT ERROR" not in diag
    assert "SCRIPT ERROR" in capsys.readouterr().err


def test_invalid_probe_limit_is_rejected_early():
    with pytest.raises(SystemExit):
        playtest.main(["--midi-seconds", "91"])

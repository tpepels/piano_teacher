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

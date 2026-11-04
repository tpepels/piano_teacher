"""Typed engine operation failures are isolated from subsequent queue work."""
import json

import pytest

from piano_teacher.inprocess import EngineCommands, OK, INVALID, FAILED
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def test_unexpected_midi_import_error_is_reported_without_killing_engine(tmp_path, monkeypatch):
    engine = PracticeEngine(tmp_path / "state", enable_midi=False)
    commands = EngineCommands(engine=engine)

    def broken_library_open(_id):
        raise OSError("invalid MIDI converter data")

    monkeypatch.setattr(engine, "load_library", broken_library_open)
    try:
        status, body = commands.request("library.open", json.dumps({"id": "broken.mid"}))
        assert status == FAILED
        assert "invalid MIDI converter data" in json.loads(body)["error"]
        status, body = commands.request("state.snapshot")
        assert status == OK and isinstance(json.loads(body), dict)
    finally:
        engine.db.close()


def test_malformed_payload_is_a_recoverable_typed_command_error(tmp_path):
    engine = PracticeEngine(tmp_path / "state", enable_midi=False)
    commands = EngineCommands(engine=engine)
    try:
        for payload in ("{bad", "[]", "{}"):
            status, body = commands.request("library.open", payload)
            assert status == INVALID and "error" in json.loads(body)
        status, body = commands.request("library.catalog")
        assert status == OK and "pieces" in json.loads(body)
    finally:
        engine.db.close()


@pytest.mark.parametrize("command", [
    {"action": "tempo", "bpm": "bad"},
    {"action": "tempo", "bpm": 0},
    {"action": "tempo", "bpm": 100000},
    {"action": "tempo", "bpm": 60.5},
    {"action": "tempo", "bpm": None},
    {"action": "hand", "hand": "unavailable"},
    {"action": "unknown-action"},
])
def test_invalid_stage_command_preserves_active_take(tmp_path, command):
    notes = (Note(0, 1, 60, 0, 0, "right", "right-source"),
             Note(0, 1, 48, 1, 0, "left", "left-source"))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(Piece(
            "Invalid commands", 100, notes, (Phrase(1, 1, 1, 0, 4, notes),),
            bar_boundaries=(0, 4)), exercise_strategy="source-progression")
        engine.fingerprint = "invalid-stage-command-fixture"
        engine.start()
        recorder = engine.recorder
        recorder.add(60, True, 0)
        before = (engine.plan.identity, engine.plan.bpm, engine.transport_id,
                  engine.score_revision, engine.visual_transport.run_at)

        status, raw = EngineCommands(engine=engine).request(
            "practice.command", json.dumps(command))

        assert status == INVALID and json.loads(raw)["error"]
        assert engine.running
        assert engine.recorder is recorder and len(recorder.presses) == 1
        assert (engine.plan.identity, engine.plan.bpm, engine.transport_id,
                engine.score_revision, engine.visual_transport.run_at) == before
    finally:
        engine.db.close()


@pytest.mark.parametrize("name", [None, 42, True, [], {}])
def test_invalid_midi_name_preserves_connected_port_and_active_take(tmp_path, name):
    class Port:
        closed = False

        def close(self):
            self.closed = True

    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        note = Note(0, 1, 60, 0, 0, "right", "source")
        engine.plan = LearningPlan(Piece(
            "Device command", 100, (note,), (Phrase(1, 1, 1, 0, 4, (note,)),),
            bar_boundaries=(0, 4)), exercise_strategy="source-progression")
        engine.fingerprint = "invalid-device-command-fixture"
        port = Port()
        engine.midi.port, engine.midi.device = port, "Current piano"
        engine.library.update(midi_device="Current piano")
        engine.start()
        recorder = engine.recorder
        recorder.add(60, True, 0)
        before = (engine.transport_id, engine.score_revision,
                  engine.visual_transport.run_at)

        status, raw = EngineCommands(engine=engine).request(
            "midi.device.select", json.dumps({"name": name}))

        assert status == INVALID and "must be text" in json.loads(raw)["error"]
        assert engine.midi.port is port and not port.closed
        assert engine.midi.device == "Current piano"
        assert engine.preferences()["midi_device"] == "Current piano"
        assert engine.running and engine.recorder is recorder
        assert len(recorder.presses) == 1
        assert (engine.transport_id, engine.score_revision,
                engine.visual_transport.run_at) == before
    finally:
        engine.db.close()

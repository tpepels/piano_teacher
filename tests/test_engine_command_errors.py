"""Typed engine operation failures are isolated from subsequent queue work."""
import json

from piano_teacher.inprocess import EngineCommands, OK, INVALID, FAILED
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

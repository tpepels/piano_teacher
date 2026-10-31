"""Engine command failures stay in-process and do not poison the queue."""
import json
from piano_teacher.inprocess import EngineCommands
from piano_teacher.server import PracticeEngine


def test_unexpected_midi_import_error_is_reported_without_killing_engine(tmp_path, monkeypatch):
    engine = PracticeEngine(tmp_path / "state", enable_midi=False)
    commands = EngineCommands(engine=engine)
    def broken_import(_path):
        raise OSError("invalid MIDI converter data")
    monkeypatch.setattr(engine, "load", broken_import)
    try:
        code, body = commands.request("POST", "/load",
                                      json.dumps({"path": "/tmp/broken.mid"}))
        assert code == 500
        assert "invalid MIDI converter data" in json.loads(body)["error"]
        code, body = commands.request("GET", "/state")
        assert code == 200 and isinstance(json.loads(body), dict)
    finally:
        engine.db.close()


def test_malformed_payload_is_a_recoverable_command_error(tmp_path):
    engine = PracticeEngine(tmp_path / "state", enable_midi=False)
    commands = EngineCommands(engine=engine)
    try:
        for payload in ("{bad", "[]", "{}"):
            status, body = commands.request("POST", "/library/open", payload)
            assert status in (400, 500) and "error" in json.loads(body)
        status, body = commands.request("GET", "/library")
        assert status == 200 and "pieces" in json.loads(body)
    finally:
        engine.db.close()

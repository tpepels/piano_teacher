"""Library/settings commands use the in-process dispatcher, not a server."""
import json
from piano_teacher.server import PracticeEngine
from piano_teacher.inprocess import EngineCommands


def test_library_and_settings_queue_commands(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    (music / "Prelude.mid").write_bytes(b"fake")
    engine = PracticeEngine(tmp_path / "state", enable_midi=False)
    commands = EngineCommands(engine=engine)

    def get(path):
        status, body = commands.request("GET", path)
        return status, json.loads(body)

    def post(path, payload):
        status, body = commands.request("POST", path, json.dumps(payload))
        return status, json.loads(body)

    try:
        assert "music_dir" in get("/settings")[1]
        status, settings = post("/settings", {"music_dir": str(music), "fullscreen": False})
        assert status == 200 and settings["fullscreen"] is False
        assert settings["music_dir"] == str(music)
        status, listing = get("/library")
        assert status == 200 and listing["count"] == 1
        assert listing["pieces"][0]["id"] == "Prelude.mid"
        status, error = post("/settings", {"music_dir": str(tmp_path / "absent")})
        assert status == 400 and "error" in error
        assert get("/settings")[1]["music_dir"] == str(music)
    finally:
        engine.db.close()

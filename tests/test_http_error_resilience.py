"""An unexpected import/converter exception returns JSON; server stays alive."""
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from piano_teacher.server import Handler, PracticeEngine


def test_exception_during_import_returns_json_and_server_survives(tmp_path, monkeypatch):
    engine = PracticeEngine(tmp_path / "state", enable_midi=False)
    class IsolatedHandler(Handler):
        pass
    IsolatedHandler.engine = engine
    server = ThreadingHTTPServer(("127.0.0.1", 0), IsolatedHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    def broken_import(path):
        raise OSError("invalid MIDI converter data")
    monkeypatch.setattr(engine, "load", broken_import)
    try:
        payload = json.dumps({"path": "/tmp/test.mid"}).encode()
        try:
            with urlopen(Request(base + "/load", data=payload,
                                 headers={"Content-Type": "application/json"}), timeout=3):
                raise AssertionError("Expected HTTP 500 for unexpected converter failure")
        except HTTPError as error:
            assert error.code == 500
            assert error.headers.get_content_type() == "application/json"
            assert "invalid MIDI converter data" in json.loads(error.read())["error"]
        with urlopen(base + "/state", timeout=3) as response:
            assert response.status == 200
            assert json.load(response)["loaded"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        engine.db.close()

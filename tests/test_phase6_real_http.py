"""Full public HTTP navigation with actual engraved PNGs, no mock endpoints."""
from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

from PIL import Image
from io import BytesIO

from piano_teacher.server import Handler, PracticeEngine

FIXTURE = Path(__file__).parent / "fixtures" / "musical_fidelity" / "midi_four_four.mid"


def test_import_open_measure_navigation_geometry_png_over_real_http(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    (music / "real.mid").write_bytes(FIXTURE.read_bytes())
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    engine.set_preferences(music_dir=str(music))

    class LocalHandler(Handler):
        pass

    LocalHandler.engine = engine
    service = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    thread = Thread(target=service.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"

    def request(route, payload=None, *, raw=False):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(base + route, body, {"Content-Type": "application/json"} if body else {})
        with urlopen(req, timeout=90) as reply:
            content = reply.read()
            return content if raw else json.loads(content)

    try:
        listed = request("/library")
        assert listed["pieces"][0]["id"] == "real.mid"
        opened = request("/library/open", {"id": "real.mid"})
        assert opened["loaded"] is True
        assert opened["piece_last_bar"] > 0
        assert opened["running"] is False
        start = min(2, opened["piece_last_bar"])
        selected = request("/control", {"action": "open_at", "bar": start,
                                        "mode": "practice"})
        assert selected["mode"] == "practice"
        assert selected["selected_start_bar"] >= start
        assert not selected["running"]
        layout = request("/score/layout")
        assert layout["notes"] and layout["systems"]
        assert layout["attack_map"]
        first = request("/score.png?page=0", raw=True)
        image = Image.open(BytesIO(first))
        image.load()
        assert image.width > 100 and image.height > 100
        assert image.getbbox() is not None
        request("/control", {"action": "next"})
        after_next = request("/state")
        assert after_next["loaded"]
        request("/control", {"action": "previous"})
        after_previous = request("/state")
        assert after_previous["loaded"]
        assert 1 <= after_previous["selected_start_bar"] <= after_previous["piece_last_bar"]
        assert not after_previous["running"]
        # The source files and user's real learner data were never modified.
        assert (music / "real.mid").read_bytes() == FIXTURE.read_bytes()
    finally:
        service.shutdown()
        service.server_close()
        thread.join(timeout=5)
        engine.db.close()

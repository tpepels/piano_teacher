"""Full in-memory command navigation with actual engraved PNGs."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from io import BytesIO

from piano_teacher.server import PracticeEngine
from piano_teacher.inprocess import EngineCommands

FIXTURE = Path(__file__).parent / "fixtures" / "musical_fidelity" / "midi_four_four.mid"


def test_import_open_measure_navigation_geometry_png_over_real_queue(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    (music / "real.mid").write_bytes(FIXTURE.read_bytes())
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    engine.set_preferences(music_dir=str(music))

    commands = EngineCommands(engine=engine)

    def request(route, payload=None, *, raw=False):
        verb = "POST" if payload is not None else "GET"
        status, data = commands.request(
            verb, route, json.dumps(payload) if payload is not None else "")
        assert status == 200, (status, data[:500])
        return data if raw else json.loads(data)

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
        engine.db.close()

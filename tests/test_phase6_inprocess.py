"""Full in-process navigation with source-owned native notation assets."""
from __future__ import annotations

import json
from pathlib import Path

from piano_teacher.server import PracticeEngine
from piano_teacher.inprocess import EngineCommands

FIXTURE = Path(__file__).parent / "fixtures" / "musical_fidelity" / "midi_four_four.mid"


def test_import_open_measure_navigation_native_notation_over_real_queue(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    (music / "real.mid").write_bytes(FIXTURE.read_bytes())
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    engine.set_preferences(music_dir=str(music))

    commands = EngineCommands(engine=engine)

    def request(route, payload=None):
        status, data = commands.request(
            route, json.dumps(payload) if payload is not None else "")
        assert status == 0, (status, data[:500])
        return json.loads(data)

    try:
        listed = request("library.catalog")
        assert listed["pieces"][0]["id"] == "real.mid"
        opened = request("library.open", {"id": "real.mid"})
        assert opened["loaded"] is True
        assert opened["piece_last_bar"] > 0
        assert opened["running"] is False
        start = min(2, opened["piece_last_bar"])
        selected = request("practice.command", {"action": "open_at", "bar": start,
                                        "mode": "practice"})
        assert selected["mode"] == "practice"
        assert selected["selected_start_bar"] >= start
        assert not selected["running"]
        layout = request("score.native_layout")
        assert layout["notes"] and layout["systems"]
        assert layout["attack_map"]
        assert layout["native_note_templates"]
        assert layout["native_glyphs"]
        assert layout["revision"] == selected["revision"]
        model = request("score.semantic")
        assert model["revision"] == selected["revision"]
        assert model["notes"]
        assert all(note["id"] for note in model["notes"])
        assert request("score.native_layout")["revision"] == model["revision"]
        request("practice.command", {"action": "next"})
        after_next = request("state.snapshot")
        assert after_next["loaded"]
        request("practice.command", {"action": "previous"})
        after_previous = request("state.snapshot")
        assert after_previous["loaded"]
        assert 1 <= after_previous["selected_start_bar"] <= after_previous["piece_last_bar"]
        assert not after_previous["running"]
        # The source files and user's real learner data were never modified.
        assert (music / "real.mid").read_bytes() == FIXTURE.read_bytes()
    finally:
        engine.db.close()

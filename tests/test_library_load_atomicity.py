"""Failed MIDI file loads must not destroy the current running session."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.smoke_phase0 import make_fixture
from piano_teacher import server
from piano_teacher.inprocess import EngineCommands
from piano_teacher.server import PracticeEngine


@pytest.mark.parametrize("failure", ["generator", "restore", "invalid_midi"])
def test_library_open_failure_preserves_existing_practice_take(
        tmp_path, monkeypatch, failure):
    folder = tmp_path / "music"
    folder.mkdir()
    first = folder / "first.mid"
    second = folder / "second.mid"
    make_fixture(first)
    make_fixture(second)
    if failure == "invalid_midi":
        second.write_bytes(b"not a valid MIDI header")
    engine = PracticeEngine(tmp_path / "app", enable_midi=False)
    bridge = EngineCommands(engine=engine)
    try:
        engine.set_preferences(music_dir=str(folder))
        status, raw = bridge.request("library.open", json.dumps({"id": first.name}))
        assert status == 0, raw
        engine.start()
        assert engine.running
        plan = engine.plan
        recorder = engine.recorder
        revision = engine.score_revision
        transport = engine.transport_id
        origin = engine.visual_transport.run_at
        source = engine.source
        fingerprint = engine.fingerprint
        score = engine.score
        last_piece = engine.library.settings["last_piece"]

        def explode(*_args, **_kwargs):
            raise ValueError("injected candidate generation failure")

        def fail_restore(*_args, **_kwargs):
            raise OSError("injected progress restoration failure")

        with monkeypatch.context() as patched:
            if failure == "generator":
                patched.setattr(server, "LearningPlan", explode)
            elif failure == "restore":
                patched.setattr(engine.progress, "restore", fail_restore)
            status, raw = bridge.request(
                "library.open", json.dumps({"id": second.name}))
            assert status != 0
            assert "error" in json.loads(raw)

        # Neither the worker callback nor the load preflight can end a valid
        # take or change the revision / source visible in the UI.
        assert engine.plan is plan
        assert engine.recorder is recorder
        assert engine.score_revision == revision
        assert engine.transport_id == transport
        assert engine.visual_transport.run_at == origin
        assert engine.source == source
        assert engine.fingerprint == fingerprint
        assert engine.score is score
        assert engine.library.settings["last_piece"] == last_piece
        assert engine.running and engine.preview_only
        assert engine.pending_result is None

        if failure != "invalid_midi":
            status, raw = bridge.request(
                "library.open", json.dumps({"id": second.name}))
            assert status == 0, raw
            assert engine.source == str(second.resolve())
            assert engine.plan is not plan
            assert engine.score_revision == revision + 1
            assert not engine.running
            assert engine.recorder is None
    finally:
        engine.db.close()

"""Failed MIDI file loads must not destroy the current running session."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.smoke_phase0 import make_fixture
from piano_teacher import server
from piano_teacher.inprocess import EngineCommands
from piano_teacher.server import PracticeEngine


@pytest.mark.parametrize("failure", ["generator", "restore", "inference", "invalid_midi"])
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
            elif failure == "inference":
                patched.setattr(engine.fingering, "prepare",
                    lambda *_args: (_ for _ in ()).throw(
                        RuntimeError("injected ONNX failure")))
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

def test_whole_piece_inference_overlaps_curriculum_without_early_publication(
        tmp_path, monkeypatch):
    """The ONNX subprocess and immutable curriculum compile independently.

    An inference stub refuses to finish before course compilation begins.
    This regression deadlocks/fails on the old serialized load, and ensures
    no incomplete fingering plan is attached to a published engine state.
    """
    from threading import Event, get_ident
    from types import SimpleNamespace
    from scripts.smoke_phase0 import make_fixture

    path=tmp_path/"overlap.mid"
    make_fixture(path)
    engine=PracticeEngine(tmp_path/"engine",enable_midi=False)
    compiled=Event()
    inference_started=Event()
    plan=SimpleNamespace(status="ready",assignments={})
    caller=get_ident()
    workers=[]
    original=server.LearningPlan

    def build(*args,**kwargs):
        compiled.set()
        return original(*args,**kwargs)

    def infer(piece,fingerprint):
        workers.append(get_ident())
        inference_started.set()
        assert compiled.wait(timeout=8), "fingering and course were serialized"
        return plan

    monkeypatch.setattr(server,"LearningPlan",build)
    monkeypatch.setattr(engine.fingering,"prepare",infer)
    try:
        old_revision=engine.score_revision
        engine.load(str(path))
        assert inference_started.is_set()
        assert workers and workers[0]!=caller
        assert engine.score_revision==old_revision+1
        assert engine.plan.piece.fingering_plan is plan
        assert engine.source==str(path.resolve())
    finally:
        engine.db.close()

"""Actual production local import with both Lumikey models installed.

Exercises the exact typed in-process commands used by the Godot GUI:
library.open -> score.native_layout -> score.semantic -> repeat open.
The original local ONNX provider must be ready, not an unavailable substitute.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import time

from piano_teacher.inprocess import EngineCommands
from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]


def test_real_moonlight_import_and_reopen_with_original_fingering_models(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    source = ROOT / "midi" / "Moonlight_Sonata_I.midi"
    assert source.is_file()
    destination = music / source.name
    shutil.copy2(source, destination)
    before_hash = hashlib.sha256(destination.read_bytes()).hexdigest()

    engine = PracticeEngine(tmp_path / "engine", enable_midi=False)
    commands = EngineCommands(engine=engine)

    def request(operation, data=None):
        status, body = commands.request(operation, json.dumps(data or {}))
        assert status == 0, (operation, status, body[-600:])
        return json.loads(body)

    try:
        request("settings.update", {
            "music_dir": str(music),
            "exercise_strategy": "coda-fukuda-midi",
        })
        started = time.perf_counter()
        opened = request("library.open", {"id": destination.name})
        first_load_seconds = time.perf_counter() - started
        assert opened["loaded"] and opened["piece_fingerprint"] == before_hash
        plan = engine.plan.piece.fingering_plan
        assert plan is not None and plan.status in {"ready", "partial"}, (
            "The original Lumikey runtime is required, not an unavailable "
            f"or fabricated fingering plan: {plan.summary() if plan else None}"
        )
        assert plan.assignments
        assert any(a.origin == "automatic" and a.finger in range(1,6)
                   for a in plan.assignments.values())
        assert first_load_seconds < 90, (
            f"Cold original MIDI import took {first_load_seconds:.2f}s")
        started = time.perf_counter()
        geometry = request("score.native_layout")
        semantic = request("score.semantic")
        ink_seconds = time.perf_counter() - started
        assert geometry["revision"] == semantic["revision"] == opened["revision"]
        assert geometry["native_note_templates"]
        assert geometry["native_glyphs"]
        assert geometry["native_beams_complete"]
        assert geometry["native_slurs_complete"]
        original_ids = {note["id"] for note in semantic["notes"]}
        written_sources = {
            event["source_id"] for event in semantic["notation_events"]
            if event.get("kind") == "note" and event.get("source_id")
        }
        assert original_ids == written_sources
        assert ink_seconds < 90, (
            f"Authentic native geometry/semantic response took {ink_seconds:.2f}s")

        revision = opened["revision"]
        started = time.perf_counter()
        reopened = request("library.open", {"id": destination.name})
        warm_seconds = time.perf_counter() - started
        assert reopened["loaded"] and reopened["revision"] > revision
        repeat_layout = request("score.native_layout")
        repeat_model = request("score.semantic")
        assert repeat_layout["revision"] == repeat_model["revision"] == reopened["revision"]
        assert repeat_layout["native_note_templates"] and repeat_model["notes"]
        assert engine.plan.piece.fingering_plan.status in {"ready", "partial"}
        assert warm_seconds < min(25, first_load_seconds + 5), (
            "Warm open failed to use cached full-piece original model plan",
            first_load_seconds, warm_seconds)
        assert destination.read_bytes() == source.read_bytes()
        print("LUMIKEY_REAL_NATIVE_OPEN:", json.dumps({
            "filename": destination.name,
            "fingered_notes": len(plan.assignments),
            "cold_open_ms": round(first_load_seconds*1000,1),
            "native_ink_ms": round(ink_seconds*1000,1),
            "warm_open_ms": round(warm_seconds*1000,1),
            "authentic_source_ids": len(original_ids),
        },sort_keys=True))
    finally:
        engine.listen.cancel()
        engine.db.close()

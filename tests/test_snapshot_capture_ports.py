"""State capture must use explicit facts/ports and retain its public schema."""
from __future__ import annotations

from dataclasses import fields

from piano_teacher.application.session_snapshot_builder import (
    SnapshotReadPorts, SnapshotValues,
)
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine
from piano_teacher.state_projection import SessionSnapshot, project_session_state


def test_unloaded_capture_keeps_public_state_and_does_not_load_score(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        with engine.lock:
            captured = engine._capture_session_snapshot()
        assert isinstance(captured, SessionSnapshot)
        assert captured.lesson is None
        assert captured.timing is None
        projected = project_session_state(captured)
        assert not projected["loaded"]
        assert projected["transport_id"] == engine.transport_id
    finally:
        engine.db.close()


def test_loaded_capture_uses_authored_preparation_gap(tmp_path, monkeypatch):
    notes = (Note(0, .5, 60, 0, 0, "right"),)
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    piece = Piece("Capture facts", 80, notes, (phrase,),
                  bar_boundaries=(0, 4),
                  time_signatures=((0, 4, 4),))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(piece)
    source_model = {"practice_timeline": {"gap": {"duration_beats": 4.0}}}
    monkeypatch.setattr(engine, "_source_model", lambda: source_model)
    try:
        with engine.lock:
            captured = engine._capture_session_snapshot()
        assert captured.lesson is not None
        assert captured.timing is not None
        assert captured.timing.practice_timeline == source_model["practice_timeline"]
        assert captured.timing.visual_gap_beats == 4.0
        assert engine.visual_transport.visual_gap_beats == 4.0
    finally:
        engine.db.close()


def test_snapshot_capture_interface_does_not_expose_engine_or_service_objects():
    facts = {field.name for field in fields(SnapshotValues)}
    ports = {field.name for field in fields(SnapshotReadPorts)}
    assert not {"engine", "midi", "library", "listen", "live_input",
                "visual_transport", "recorder", "teaching"} & facts
    assert {"source_model", "elapsed_beat", "phase", "listen_snapshot",
            "preparation_schedule", "set_visual_gap_beats"} <= ports

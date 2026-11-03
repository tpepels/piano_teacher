"""Long-session invariants for the real in-process worker and transport clock.

All time is a deterministic monotonic clock. This does not claim to validate
Bluetooth/USB scheduling or the actual timing of a human performance.
"""
from __future__ import annotations

import json

import pytest

from piano_teacher import server
from piano_teacher.inprocess import EngineCommands
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def _preview_engine(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    notes = (
        Note(0, .5, 60, 0, 0, "right", "cycle-a"),
        Note(1, 1.5, 62, 0, 0, "right", "cycle-b"),
        Note(3, 3.5, 64, 0, 0, "right", "cycle-c"),
    )
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    piece = Piece("Long session with written rest", 90, notes, (phrase,),
                  bar_boundaries=(0, 4), time_signatures=((0, 4, 4),))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(piece)
    engine.start()
    assert engine.preview_only
    return engine, EngineCommands(engine=engine), clock


def test_250_worker_driven_previews_survive_long_pauses_without_scroll_drift(
        tmp_path, monkeypatch):
    engine, commands, clock = _preview_engine(tmp_path, monkeypatch)
    try:
        revision = engine.score_revision
        original_transport = engine.transport_id
        source_beats = engine.plan.active_phrase.end - engine.plan.active_phrase.start
        seconds_per_beat = 60 / engine.plan.bpm
        expected_offset = engine.visual_transport.visual_offset_beats
        stride = engine._source_model()["practice_timeline"]["stride_beats"]
        assert stride == source_beats + engine.visual_transport.visual_gap_beats

        for cycle in range(250):
            origin = engine.visual_transport.run_at
            if cycle % 25 == 0:
                # Simulate a 10-minute application suspension during a pause.
                clock[0] = origin + 0.75
                engine.control("pause")
                assert commands.tick() == 250
                transport = engine.transport_id
                clock[0] += 600
                assert commands.tick() == 250
                assert engine.transport_id == transport
                engine.control("resume")
                assert engine.visual_transport.run_at == pytest.approx(origin + 600)
                origin = engine.visual_transport.run_at

            clock[0] = origin + source_beats * seconds_per_beat + 0.01
            assert commands.tick() == 20
            assert engine.visual_transport._preview_loop_pending
            gap_deadline = engine.visual_transport.next_at
            assert gap_deadline == pytest.approx(
                origin + (source_beats +
                          engine.visual_transport.visual_gap_beats) * seconds_per_beat)
            clock[0] = gap_deadline + 0.01
            assert commands.tick() == 20
            expected_offset += stride
            assert engine.visual_transport.visual_offset_beats == pytest.approx(
                expected_offset, abs=1e-7)
            assert engine.visual_transport.run_at == pytest.approx(gap_deadline)
            assert engine.transport_id == original_transport + cycle + 1
            assert engine.running and engine.preview_only
            assert not engine.visual_transport.paused
            assert engine.pending_result is None
            assert engine.recorder is not None and not engine.recorder.presses
            assert engine.score_revision == revision
            if cycle % 50 == 0:
                snapshot = engine.state()
                assert snapshot["running"] and snapshot["preview_only"]
                assert snapshot["visual_offset_beats"] == pytest.approx(expected_offset)
                assert snapshot["midi_notes"] == 0
                assert snapshot["mastered"] == 0
        # Preview is not graded; 250 repeats must not generate learner records.
        assert engine.db.execute(
            "SELECT count(*) FROM practice_evidence").fetchone()[0] == 0
        assert engine.db.execute(
            "SELECT count(*) FROM mastery").fetchone()[0] == 0
    finally:
        engine.db.close()


def test_rapid_pause_resume_and_worker_ticks_never_advance_a_frozen_take(
        tmp_path, monkeypatch):
    engine, commands, clock = _preview_engine(tmp_path, monkeypatch)
    try:
        origin = engine.visual_transport.run_at
        for index in range(100):
            # Repeated short pauses produce a known additive absolute offset.
            clock[0] = origin + 0.25
            engine.control("pause")
            held_beat = engine.state()["clock_beat"]
            for _ in range(4):
                clock[0] += 0.4
                assert commands.tick() == 250
                assert engine.state()["clock_beat"] == pytest.approx(held_beat)
            engine.control("resume")
            origin = engine.visual_transport.run_at
            assert origin == pytest.approx(1000.0 + (index + 1) * 1.6, abs=1e-7)
            assert engine.pending_result is None
        assert engine.transport_id == 1
        assert engine.visual_transport.visual_offset_beats == 0
        assert engine.score_revision == 0
    finally:
        engine.db.close()

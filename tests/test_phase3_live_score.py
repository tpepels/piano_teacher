"""Real engraving -> MIDI recording -> state -> individual red notehead marks.

Runs without a hardware piano. The isolated engine is given a virtual MIDI
connection; the production API still never fabricates student input.
"""
from __future__ import annotations

import time

from piano_teacher.server import PracticeEngine
from piano_teacher.warmups import materialize


def _engine(tmp_path: object, hand: str) -> PracticeEngine:
    from pathlib import Path

    root = Path(tmp_path)
    path = materialize("warmup:chords", root / "music")
    engine = PracticeEngine(root / "data", enable_midi=False)
    engine.load(str(path), warmup=True)
    engine.plan.set_hand(hand)
    # Force real canonical Verovio mapping, instead of mocked coordinates.
    layout = engine.geometry()
    assert layout["mapping_schema"] == "source-note-v1"
    engine.midi.port = object()  # Isolated in-process test instrument only.
    engine.start()
    # At 68 BPM, the allowed onset window for beat zero has expired after
    # 0.65 beats, before a two-beat half-note is released.
    engine.run_at = time.monotonic() - 0.85
    return engine


def test_complete_miss_produces_real_engraved_red_marker_and_hud(tmp_path):
    engine = _engine(tmp_path, "left")
    try:
        state = engine.state()
        assert state["phase"] == "playing"
        assert state["scoring_available"] and not state["preview_only"]
        misses = [mark for mark in state["feedback_marks"] if mark["status"] == "missed"]
        assert len(misses) == 1
        assert misses[0]["pitch"] == 48
        assert misses[0]["source_id"]
        assert misses[0]["note_id"] in {
            note["id"] for note in engine.geometry()["notes"]
        }
        assert state["live_note_feedback"] == {
            "status": "missed", "pitch": 48, "name": "C3", "count": 1,
            "source_id": misses[0]["source_id"],
        }
    finally:
        engine.db.close()


def test_partially_played_chord_only_marks_unplayed_notehead(tmp_path):
    engine = _engine(tmp_path, "right")
    try:
        assert engine.recorder is not None
        engine.recorder.add(60, True, 0.02)
        engine.recorder.add(64, True, 0.03)
        state = engine.state()
        marks = state["feedback_marks"]
        misses = [mark for mark in marks if mark["status"] in ("wrong", "missed")]
        assert [(mark["pitch"], mark["status"]) for mark in misses] == [(67, "missed")]
        assert not any(mark["pitch"] in (60, 64) and mark["status"] in ("missed", "wrong")
                       for mark in marks)
        assert state["live_note_feedback"]["name"] == "G4"
    finally:
        engine.db.close()


def test_unconnected_preview_explicitly_disables_note_assessment(tmp_path):
    path = materialize("warmup:chords", tmp_path / "music")
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    try:
        engine.load(str(path), warmup=True)
        engine.geometry()
        engine.start()
        engine.run_at = time.monotonic() - .85
        state = engine.state()
        assert state["preview_only"]
        assert not state["scoring_available"]
        assert state["live_note_feedback"] is None
        assert not state["feedback_marks"]
    finally:
        engine.db.close()

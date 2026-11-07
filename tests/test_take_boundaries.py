"""Every new transport epoch starts with fresh take-scoped state.

The take boundary is where feedback bugs clustered: a new transport ID
coexisting with the previous take's recorder, live MIDI matches or marks.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def engine(tmp_path):
    now = [100.0]
    notes = tuple(Note(float(i), float(i + 1), pitch, 0, 0, "right", f"n{i}")
                  for i, pitch in enumerate((60, 62, 64, 65)))
    piece = Piece("Boundaries", 80, notes, (Phrase(1, 1, 1, 0, 4, notes),),
                  bar_boundaries=(0, 4))
    engine = PracticeEngine(tmp_path, enable_midi=False, clock=lambda: now[0])
    engine.plan = LearningPlan(piece, exercise_strategy="source-progression")
    engine.fingerprint = "boundaries"
    engine.midi.port = SimpleNamespace(closed=False)
    engine.test_clock = now
    yield engine
    engine.db.close()


def _dirty_take(engine):
    engine.start()
    engine.test_clock[0] = engine.visual_transport.run_at + .01
    engine._receive(SimpleNamespace(type="note_on", note=60, velocity=80, channel=0))
    engine.feedback_marks = [{"note_id": "stale", "status": "missed"}]
    engine.live_assessment.latest_marks = [{"note_id": "stale"}]
    assert engine.live_input.used and engine.recorder.presses
    return engine.transport_id


def _assert_fresh(engine, previous_transport):
    assert engine.transport_id == previous_transport + 1
    assert not engine.live_input.used
    assert engine.feedback_marks == [] and engine.feedback_unmapped == 0
    assert engine.live_assessment.latest_marks == []
    assert engine.pending_result is None


def test_restarting_practice_opens_a_clean_take(engine):
    previous = _dirty_take(engine)
    engine.start()
    _assert_fresh(engine, previous)
    assert engine.recorder is not None and not engine.recorder.presses


def test_entering_guided_learning_opens_a_clean_take(engine):
    previous = _dirty_take(engine)
    engine._begin_learn()
    _assert_fresh(engine, previous)
    assert engine.recorder is None


def test_transport_epoch_advances_only_in_open_take():
    tree = ast.parse((ROOT / "piano_teacher/server.py").read_text())
    owners = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if (isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Attribute)
                    and node.target.attr == "transport_id"):
                owners.append(function.name)
    assert owners == ["_open_take"]

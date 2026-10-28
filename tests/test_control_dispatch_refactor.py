"""Characterization of the public command dispatcher after handler extraction."""
from __future__ import annotations

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


@pytest.fixture
def app(tmp_path):
    notes = (Note(0, 1, 60, 0, 0, "right"),
             Note(1, 2, 64, 0, 0, "right"),
             Note(0, 2, 48, 1, 0, "left"))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(Piece("Dispatch", 100, notes, (phrase,),
                                     bar_boundaries=(0, 4, 8)))
    try:
        yield engine
    finally:
        engine.db.close()


def test_pause_resume_and_restart_are_dispatched_without_changing_score(app):
    app.control("start")
    assert app.state()["phase"] == "count_in"
    app.control("pause")
    state = app.state()
    assert state["phase"] == "paused" and state["paused"] is True
    assert state["visual_scroll_speed"] == 0
    with pytest.raises(ValueError, match="already paused"):
        app.control("pause")
    app.control("resume")
    assert app.state()["phase"] == "count_in"
    with pytest.raises(ValueError, match="unless an exercise is paused"):
        app.control("resume")
    app.control("stop")
    assert app.state()["phase"] == "ready" and not app.running


def test_stage_commands_preserve_validation_and_revision_contract(app):
    revision = app.score_revision
    with pytest.raises(ValueError, match="whole lesson step"):
        app.control("select_step", number=1.25)
    assert app.score_revision == revision
    app.control("tempo", bpm=80)
    assert app.plan.bpm == 80 and app.score_revision == revision
    app.control("tempo_down")
    assert app.plan.bpm == 75 and app.score_revision == revision
    app.control("select_step", number="1")
    assert app.plan.lesson_step_number == 1
    assert app.score_revision == revision + 1
    with pytest.raises(ValueError, match="Unsupported action"):
        app.control("not_a_real_action")


def test_open_measure_validation_precedes_state_mutation(app):
    before = app.score_revision
    with pytest.raises(ValueError, match="whole measure"):
        app.control("open_at", bar="1", mode="practice")
    with pytest.raises(ValueError, match="Choose Learn Notes"):
        app.control("open_at", bar=1, mode="unknown")
    assert app.score_revision == before
    assert app.mode == "practice"

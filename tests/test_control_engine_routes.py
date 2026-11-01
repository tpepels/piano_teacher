"""Real engine command routing: protected state and error contracts."""
import pytest

from piano_teacher.server import PracticeEngine
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece


def _sample_plan():
    notes = (Note(0, .5, 60, 0, 0, "right"),)
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    piece = Piece("Control routing", 80, notes, (phrase,),
                  bar_boundaries=(0, 4), time_signatures=((0, 4, 4),))
    return LearningPlan(piece)


def test_unloaded_commands_retain_original_validation(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        with pytest.raises(ValueError, match="Open a piece first"):
            engine.control("start")
        with pytest.raises(ValueError, match="Open a piece first"):
            engine.control("select_step", number=1)
        with pytest.raises(ValueError, match="Find the current notes"):
            engine.control("learn_next")
        engine.control("score_ready", revision=9999)
        engine.control("demo_ready", token="stale")
        engine.control("hints", enabled=True)
        assert engine.persistent_hints
        assert engine.guided_session.persistent_hints
        engine.control("stop")
        assert engine.feedback == "Stopped"
        assert engine.next_action == "Start when you are ready."
    finally:
        engine.db.close()


def test_source_stage_commands_stay_under_existing_lock(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = _sample_plan()
    try:
        prior_revision = engine.score_revision
        with pytest.raises(ValueError, match="whole lesson step"):
            engine.control("select_step", number=1.5)
        assert engine.score_revision == prior_revision
        engine.control("select_step", number="1")
        assert engine.score_revision == prior_revision + 1
        with pytest.raises(ValueError, match="Unsupported action"):
            engine.control("undefined_control_action")
        engine.control("stop")
        assert not engine.running
    finally:
        engine.db.close()

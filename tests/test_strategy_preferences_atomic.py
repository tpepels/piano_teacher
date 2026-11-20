"""Atomic preference publication: a rejected strategy or a failed settings
write leaves the course and the saved settings intact."""
from __future__ import annotations

from pathlib import Path

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.library import ScoreLibrary
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def _piece():
    notes = (
        Note(0, .5, 60, 0, 0, "right", "first"),
        Note(1, 1.5, 62, 0, 0, "right", "second"),
    )
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    return Piece("Switch contract", 100, notes, (phrase,),
                 bar_boundaries=(0, 4), time_signatures=((0, 4, 4),))


def test_proposed_library_settings_are_validated_without_side_effects(tmp_path):
    library = ScoreLibrary(tmp_path)
    library.update(metronome=True)
    before = dict(library.settings)
    disk = library.settings_path.read_bytes()
    candidate = library.propose_update(metronome=False)
    assert candidate["metronome"] is False
    assert candidate["exercise_strategy"] == "practice-flow"
    assert library.settings == before
    assert library.settings_path.read_bytes() == disk
    for rejected in ("deleted-legacy", "coda-midi", "source-progression"):
        with pytest.raises(ValueError, match="Unknown exercise strategy"):
            library.propose_update(exercise_strategy=rejected)
    assert library.settings == before
    assert library.settings_path.read_bytes() == disk


def test_failed_settings_write_cannot_change_live_library(tmp_path, monkeypatch):
    library = ScoreLibrary(tmp_path)
    library.update(metronome=True)
    before = dict(library.settings)
    disk = library.settings_path.read_bytes()

    def cannot_save(**_kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(library, "save", cannot_save)
    with pytest.raises(OSError, match="disk full"):
        library.update(metronome=False)
    assert library.settings == before
    assert library.settings_path.read_bytes() == disk


def test_rejected_strategy_preserves_live_transport_and_preferences(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.set_preferences(metronome=True)
        engine.plan = LearningPlan(_piece())
        engine.fingerprint = "switch-fixture"
        engine.start()
        plan = engine.plan
        recorder = engine.attempt.recorder
        transport_id = engine.transport_id
        revision = engine.score_revision
        run_at = engine.visual_transport.run_at
        before = dict(engine.library.settings)
        disk = engine.library.settings_path.read_bytes()
        with pytest.raises(ValueError, match="Unknown exercise strategy"):
            engine.set_preferences(exercise_strategy="coda-midi")
        assert engine.library.settings == before
        assert engine.library.settings_path.read_bytes() == disk
        assert engine.plan is plan
        assert engine.attempt.recorder is recorder
        assert engine.running
        assert engine.transport_id == transport_id
        assert engine.score_revision == revision
        assert engine.visual_transport.run_at == run_at
    finally:
        engine.db.close()


def test_failed_settings_write_keeps_active_session(tmp_path, monkeypatch):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(_piece())
        engine.fingerprint = "switch-fixture"
        engine.start()
        plan = engine.plan
        revision = engine.score_revision
        before = dict(engine.library.settings)

        def cannot_save(**_kwargs):
            raise OSError("simulated settings write failure")

        monkeypatch.setattr(engine.library, "save", cannot_save)
        with pytest.raises(OSError, match="settings write"):
            engine.set_preferences(metronome=not before["metronome"])
        assert engine.library.settings == before
        assert engine.plan is plan
        assert engine.running
        assert engine.score_revision == revision
    finally:
        engine.db.close()


def test_reselecting_the_default_strategy_keeps_the_running_course(tmp_path):
    """Choosing the strategy that is already active never rebuilds or
    interrupts the course."""
    from piano_teacher.music import load_midi

    source = (Path(__file__).resolve().parents[1] / "midi"
              / "J_S_Bach_-_Invention_No_1_(BWV_772).midi")
    engine = PracticeEngine(tmp_path / "app", enable_midi=False)
    try:
        engine.plan = LearningPlan(
            load_midi(source), exercise_strategy="coda-fukuda-midi")
        engine.fingerprint = "real-midi-strategy-fixture"
        engine.start()
        old_plan = engine.plan
        old_revision = engine.score_revision

        response = engine.set_preferences(
            exercise_strategy="coda-fukuda-midi")
        assert response["exercise_strategy"] == "coda-fukuda-midi"
        assert engine.plan is old_plan
        assert engine.running and engine.attempt.recorder is not None
        assert engine.score_revision == old_revision
        assert ScoreLibrary(tmp_path / "app" / "config").settings[
            "exercise_strategy"] == "coda-fukuda-midi"
    finally:
        engine.db.close()

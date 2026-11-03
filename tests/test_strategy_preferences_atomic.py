"""Atomic preference publication and failure-safe strategy switching."""
from __future__ import annotations

import json

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
    library.update(exercise_strategy="source-progression")
    before = dict(library.settings)
    disk = library.settings_path.read_bytes()
    candidate = library.propose_update(exercise_strategy="coda-midi")
    assert candidate["exercise_strategy"] == "coda-midi"
    assert candidate["timing_strategy"] == "original-timing"
    assert candidate["tempo_strategy"] == "constant-tempo"
    assert library.settings == before
    assert library.settings_path.read_bytes() == disk
    with pytest.raises(ValueError, match="Unknown exercise strategy"):
        library.propose_update(exercise_strategy="deleted-legacy")
    assert library.settings == before


def test_failed_settings_write_cannot_change_live_library(tmp_path, monkeypatch):
    library = ScoreLibrary(tmp_path)
    library.update(exercise_strategy="source-progression")
    before = dict(library.settings)
    disk = library.settings_path.read_bytes()

    def cannot_save(**_kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(library, "save", cannot_save)
    with pytest.raises(OSError, match="disk full"):
        library.update(exercise_strategy="coda-midi")
    assert library.settings == before
    assert library.settings_path.read_bytes() == disk


def test_failed_strategy_construction_preserves_live_transport_and_preferences(
        tmp_path, monkeypatch):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.set_preferences(exercise_strategy="source-progression")
        engine.plan = LearningPlan(_piece(), exercise_strategy="source-progression")
        engine.fingerprint = "switch-fixture"
        engine.start()
        plan = engine.plan
        recorder = engine.recorder
        transport_id = engine.transport_id
        revision = engine.score_revision
        run_at = engine.run_at
        before = dict(engine.library.settings)
        disk = engine.library.settings_path.read_bytes()

        def fail_generator(*_args, **_kwargs):
            raise ValueError("simulated generator failure")

        monkeypatch.setattr("piano_teacher.server.restored_strategy_plan",
                            fail_generator)
        with pytest.raises(ValueError, match="generator failure"):
            engine.set_preferences(exercise_strategy="coda-midi")
        assert engine.library.settings == before
        assert engine.library.settings_path.read_bytes() == disk
        assert engine.plan is plan
        assert engine.recorder is recorder
        assert engine.running
        assert engine.transport_id == transport_id
        assert engine.score_revision == revision
        assert engine.run_at == run_at
    finally:
        engine.db.close()


def test_failed_settings_write_keeps_active_session_even_after_preflight(
        tmp_path, monkeypatch):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.set_preferences(exercise_strategy="source-progression")
        engine.plan = LearningPlan(_piece(), exercise_strategy="source-progression")
        engine.fingerprint = "switch-fixture"
        engine.start()
        plan = engine.plan
        revision = engine.score_revision
        before = dict(engine.library.settings)

        def cannot_save(**_kwargs):
            raise OSError("simulated settings write failure")

        monkeypatch.setattr(engine.library, "save", cannot_save)
        with pytest.raises(OSError, match="settings write"):
            engine.set_preferences(exercise_strategy="coda-midi")
        assert engine.library.settings == before
        assert engine.plan is plan
        assert engine.running
        assert engine.score_revision == revision
    finally:
        engine.db.close()

"""Fast, hardware-free verification of experimental strategy contracts."""
import sqlite3

import pytest

from piano_teacher.exercise_contracts import (
    AssessmentEvidence, DottedPairTiming, ErrorFamilyDiagnosis,
    LearnerSnapshot, OriginalTiming, RepeatedErrorPolicy, assess_timed,
)
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.library import ScoreLibrary
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote
from piano_teacher.practice_history import AssessmentHistoryStore, PracticePolicyService
from piano_teacher.server import PracticeEngine
from piano_teacher.learning import LearningPlan


def simple_piece():
    notes = tuple(Note(float(i), float(i+1), 60+i, 0, 0, "right", f"src-{i}", "v1")
                  for i in range(4))
    phrase = Phrase(1, 1, 1, 0., 4., notes)
    return Piece("Four", 80, notes, (phrase,))


def variant():
    piece = simple_piece()
    return ExerciseVariant("original", piece.phrases[0], tuple(range(4)))


def test_dotted_timing_map_preserves_source_and_pair_duration():
    source = variant()
    original = OriginalTiming().transform(source)
    altered = DottedPairTiming().transform(source)
    assert original.exercise_phrase.notes == source.notes
    assert [e.source_index for e in altered.events] == list(range(4))
    assert altered.exercise_phrase.notes[0].end == 1.5
    assert altered.exercise_phrase.notes[1].start == 1.5
    assert altered.exercise_phrase.notes[2].end == 3.5
    assert altered.exercise_phrase.notes[3].start == 3.5
    assert altered.exercise_phrase.notes[3].end == 4.0
    assert source.notes[0].end == 1.0
    assert [n.source_id for n in altered.exercise_phrase.notes] == [
        n.source_id for n in source.notes]


def test_timed_grading_uses_transformed_onsets_but_reports_original_notes():
    plan = DottedPairTiming().transform(variant())
    played = [PlayedNote(n.pitch, n.start, n.end) for n in plan.exercise_phrase.notes]
    result = assess_timed(plan, "right", 60, played)
    assert result.assessment.clean
    assert result.assessment.notes[1].note.start == 1.0
    played[1] = PlayedNote(played[1].pitch, 1.0, 2.0)
    incorrect = assess_timed(plan, "right", 60, played)
    assert not incorrect.assessment.clean


def test_polyphonic_material_is_not_retimed():
    source = variant()
    other = Note(0, 1, 48, 1, 0, "left", "bass", "v1")
    phrase = Phrase(1, 1, 1, 0, 4, source.notes+(other,))
    mixed = ExerciseVariant("original", phrase, tuple(range(5)))
    assert DottedPairTiming().transform(mixed).exercise_phrase.notes == mixed.notes


def test_timing_contract_rejects_unmapped_source_events():
    from dataclasses import replace
    plan = OriginalTiming().transform(variant())
    with pytest.raises(ValueError, match="source mapping"):
        replace(plan, events=(replace(plan.events[0], source_index=99), *plan.events[1:]))


def test_history_is_persistent_scoped_and_bounded(tmp_path):
    db_path = tmp_path / "history.db"
    db = sqlite3.connect(db_path)
    store = AssessmentHistoryStore(db)
    policy = PracticePolicyService(store)
    bad = AssessmentEvidence("stage-fukuda", ("late", "late", "correct"), 0, 60.)
    assert policy.observe("score", bad).action == "repeat"
    assert policy.observe("score", bad).action == "timing-practice"
    assert policy.inspect("score", "stage-fukuda")["latest_diagnosis"] == "rhythm"
    assert not store.recent("score", "stage-legacy").recent
    for _ in range(70):
        store.record("score", bad)
    assert len(store.recent("score", "stage-fukuda", 64).recent) == 64
    db.close()
    reopened = sqlite3.connect(db_path)
    assert len(AssessmentHistoryStore(reopened).recent("score", "stage-fukuda").recent) == 8
    reopened.close()


def test_diagnosis_not_credited_without_actual_assessment():
    evidence = AssessmentEvidence("a", ("correct",), 0, 60, assessed=False)
    assert not evidence.clean
    with pytest.raises(ValueError):
        LearnerSnapshot("a", (evidence,))
    assert ErrorFamilyDiagnosis().diagnose(evidence) == "unassessed"
    assert RepeatedErrorPolicy().recommend(LearnerSnapshot("a", ()),
                                          ErrorFamilyDiagnosis()).action == "repeat"


def test_strategy_settings_validate_and_persist(tmp_path):
    config = tmp_path / "config"
    library = ScoreLibrary(config)
    choices = {item["id"] for item in library.public_settings()["available_exercise_strategies"]}
    assert "fukuda+coda-part" in choices
    library.update(exercise_strategy="fukuda")
    assert ScoreLibrary(config).settings["exercise_strategy"] == "fukuda"
    with pytest.raises(ValueError):
        library.update(exercise_strategy="nonexistent")
    assert ScoreLibrary(config).settings["exercise_strategy"] == "fukuda"


def test_live_strategy_switch_rebuilds_plan_without_transferring_mastery(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        source = simple_piece()
        engine.plan = LearningPlan(source, exercise_strategy="legacy")
        engine.fingerprint = "synthetic-hash"
        legacy_key = engine.plan.identity
        engine.plan.mastered[legacy_key] = 80
        engine._save()
        options = engine.set_preferences(exercise_strategy="fukuda")
        assert options["exercise_strategy"] == "fukuda"
        assert engine.plan.exercise_strategy.name == "fukuda"
        assert legacy_key != engine.plan.identity
        assert engine.plan.identity not in engine.plan.mastered
        assert engine.plan.streak == 0
        assert engine.score_revision > 0
        engine.set_preferences(exercise_strategy="legacy")
        assert engine.plan.exercise_strategy.name == "legacy"
        assert legacy_key in engine.plan.mastered
        assert engine.plan.identity == legacy_key
    finally:
        engine.db.close()


def test_environment_no_longer_overrides_saved_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("PIANO_EXERCISE_STRATEGY", "coda-part")
    piece = simple_piece()
    assert LearningPlan(piece).exercise_strategy.name == "legacy"
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.set_preferences(exercise_strategy="fukuda")
        engine.plan = LearningPlan(piece,
            exercise_strategy=engine.library.settings["exercise_strategy"])
        assert engine.plan.exercise_strategy.name == "fukuda"
    finally:
        engine.db.close()

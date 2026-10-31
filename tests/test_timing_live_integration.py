"""Fast timing-strategy integration checks; no audio device or corpus audits."""
from dataclasses import replace

import pytest

from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
from piano_teacher.exercise_contracts import OriginalTiming, TwoPhaseTempo, assess_timed
from piano_teacher.learning import LearningPlan
from piano_teacher.library import ScoreLibrary
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.server import PracticeEngine


def score():
    notes = tuple(Note(float(i), float(i+1), 60+i, 0, 0,
                       "right", f"source-{i}", "voice-1") for i in range(4))
    return Piece("Timing fixture", 80, notes, (Phrase(1, 1, 1, 0, 4, notes),))


def stage(plan, level):
    matches = [i for i, item in enumerate(plan.variants) if item.level == level]
    assert len(matches) == 1
    plan.variant_index = matches[0]
    return plan.active_variant


@pytest.mark.parametrize("pattern,changed_attack", [
    ("dotted-long-short", 1.5),
    ("dotted-short-long", .5),
])
def test_dotted_drills_change_native_score_and_keep_original_required(pattern, changed_attack, tmp_path):
    piece = score()
    plan = LearningPlan(piece, timing_strategy=pattern)
    assert plan.variants[-1].level == "original"
    original_key = plan.lesson_steps[-1].key
    drill = stage(plan, pattern)
    assert drill.notes[1].start == pytest.approx(changed_attack)
    assert [n.source_id for n in drill.notes] == [n.source_id for n in piece.notes]
    assert tuple(n.start for n in piece.notes) == (0, 1, 2, 3)
    assert original_key != plan.identity
    artifact = ScoreArtifacts(PreprocessingCache(tmp_path / "preprocessed"))
    selected = ScoreSelection(piece, drill.phrase, "right", plan.identity, 1, "fixture")
    model = artifact.source_model(selected)
    events = {n["id"]: n for n in model["notes"]}
    assert events["source-1"]["onset_beats"] == pytest.approx(changed_attack)
    assert {n["id"] for n in model["notes"]} == {n.source_id for n in piece.notes}


def test_two_phase_clock_and_grading_agree_on_note_times(tmp_path):
    piece = score()
    plan = LearningPlan(piece, tempo_strategy="two-phase-tempo")
    source = stage(plan, "two-phase-tempo")
    plan.bpm = 60
    timing = OriginalTiming().transform(source)
    tempo = TwoPhaseTempo().generate(timing, plan.bpm)
    played = [PlayedNote(n.pitch, tempo.seconds_at(n.start),
                         tempo.seconds_at(n.end)) for n in source.notes]
    assert assess_timed(timing, "right", 60, played, tempo_map=tempo).assessment.clean
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = plan
        engine.mode = "practice"
        assert engine._elapsed_seconds(2) == pytest.approx(2*60/48)
        assert engine._elapsed_beat(engine._elapsed_seconds(4)) == pytest.approx(4)
    finally:
        engine.db.close()


def test_combined_timing_stage_still_requires_original_mastery():
    plan = LearningPlan(score(), timing_strategy="dotted-long-short",
                        tempo_strategy="two-phase-tempo")
    levels = [v.level for v in plan.variants]
    assert "dotted-long-short" in levels
    assert "two-phase-tempo" in levels
    assert "dotted-long-short+two-phase-tempo" in levels
    assert levels[-1] == "original"
    assert len({step.key for step in plan.lesson_steps}) == len(plan.lesson_steps)


def test_settings_persist_independent_timing_axes(tmp_path):
    cfg = tmp_path / "cfg"
    library = ScoreLibrary(cfg)
    library.update(timing_strategy="dotted-short-long", tempo_strategy="two-phase-tempo")
    reopened = ScoreLibrary(cfg)
    assert reopened.settings["timing_strategy"] == "dotted-short-long"
    assert reopened.settings["tempo_strategy"] == "two-phase-tempo"
    with pytest.raises(ValueError):
        library.update(timing_strategy="invalid")
    assert "dotted-long-short" in {
        row["id"] for row in reopened.public_settings()["available_timing_strategies"]}


def test_changing_rhythm_resets_active_path_and_restores_previous_profile(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.fingerprint = "timing-fixture"
        engine.plan = LearningPlan(score(), exercise_strategy="coda-part")
        baseline_key = engine.plan.identity
        engine._save()
        engine.set_preferences(timing_strategy="dotted-long-short")
        assert engine.plan.profile == "coda-part~dotted-long-short"
        stage(engine.plan, "dotted-long-short")
        transformed_key = engine.plan.identity
        engine.plan.bpm = 55
        engine._save()
        engine.set_preferences(timing_strategy="original-timing")
        assert engine.plan.identity == baseline_key
        engine.set_preferences(timing_strategy="dotted-long-short")
        assert engine.plan.identity == transformed_key
        assert engine.plan.bpm == 55
    finally:
        engine.db.close()

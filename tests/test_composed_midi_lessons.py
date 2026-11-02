"""Composed MIDI curriculum, registration, feedback, persistence and real playback."""
from dataclasses import replace
from pathlib import Path

import mido
import pytest

from piano_teacher.application.listen_session import ListenSelection, ListenSession
from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
from piano_teacher.assessment_clock import expected_note_seconds
from piano_teacher.exercise_contracts import ConstantTempo, OriginalTiming
from piano_teacher.exercise_strategies import available_strategies, resolve_strategy
from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_generators import (
    CodaFukudaMidiLessonGenerator, CodaLessonGenerator,
    LessonGeneratorRegistration, register_lesson_generator,
    compose_lesson_definitions,
)
from piano_teacher.music import load_midi
from piano_teacher.practice import Assessment, NoteAssessment, PlayedNote, evaluate
from piano_teacher.preprocessing_cache import PreprocessingCache


def write_piece(path: Path) -> None:
    """Four actual measures, both hands, chord reductions and even eighths."""
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    for hand in ("Right Hand", "Left Hand"):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=hand, time=0))
        track.append(mido.MetaMessage("time_signature",
                                      numerator=4, denominator=4, time=0))
        events = []
        for i in range(32):
            tick = i * 240
            pitch = 60 + (i % 7) if hand == "Right Hand" else 43 + i % 4
            events.extend(((tick, True, pitch), (tick + 240, False, pitch)))
        if hand == "Right Hand":
            for p in (48, 55, 67, 72):
                events.extend(((0, True, p), (240, False, p)))
        last = 0
        for tick, on, pitch in sorted(events, key=lambda x: (x[0], x[1])):
            track.append(mido.Message(
                "note_on" if on else "note_off", note=pitch,
                velocity=80 if on else 0, time=tick - last))
            last = tick
        track.append(mido.MetaMessage("end_of_track", time=7680-last))
        midi.tracks.append(track)
    midi.save(path)


@pytest.fixture
def piece(tmp_path):
    path = tmp_path / "both-hands.mid"
    write_piece(path)
    return load_midi(path)


def test_hybrid_is_a_selectable_midi_only_strategy(piece):
    available = {item["id"] for item in available_strategies()}
    assert "coda-fukuda-midi" in available
    assert resolve_strategy("coda-fukuda-midi", piece=piece).name == "coda-fukuda-midi"
    with pytest.raises(ValueError, match="MIDI piece"):
        resolve_strategy("coda-fukuda-midi")
    assert isinstance(LearningPlan(piece, exercise_strategy="coda-fukuda-midi").lesson_generator,
                      CodaFukudaMidiLessonGenerator)


def test_hybrid_preserves_both_research_families_and_source_final(piece):
    coda = LearningPlan(piece, exercise_strategy="coda-midi")
    combined = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    assert combined.lesson_definition.requires_unique_source_ids
    assert len([ex for ex in combined.exercises if ex.kind=="learn"]) >= 2
    assert all(ex.phrase.last_bar-ex.phrase.first_bar <= 1
               for ex in combined.exercises if ex.kind=="learn")
    assert combined.exercises[-1].kind == "perform"
    assert combined.exercises[-1].phrase.notes == piece.notes
    assert all(s.key.startswith("course:2:coda-fukuda-midi:") for s in
               combined.lesson_steps)
    assert combined.lesson_generator.catalog is not None
    catalog = combined.lesson_generator.catalog
    assert any(s.variant.level.startswith("fukuda-midi-")
               for sequence in catalog.stage_sequences.values() for s in sequence)
    assert any(s.variant.level.startswith("coda-dotted-")
               for sequence in catalog.stage_sequences.values() for s in sequence)
    assert any(s.variant.level.startswith("coda-chord-")
               for sequence in catalog.stage_sequences.values() for s in sequence)
    assert any(s.variant.level.startswith("coda-slowdown-x2")
               for sequence in catalog.stage_sequences.values() for s in sequence)
    for ex in combined.exercises:
        for hand in ex.hands or ("right", "left", "both"):
            if (ex.key,hand) not in combined.lesson_definition.stage_sequences:
                continue
            stages = combined.lesson_definition.stages(ex,hand)
            assert stages[-1].variant.level == "original"
            original = stages[-1].variant.notes
            assert original == tuple(n for n in ex.phrase.notes
                                     if hand == "both" or n.hand == hand)
            assert all(set(n.source_id for n in v.variant.notes) <=
                       set(n.source_id for n in original) for v in stages)
    assert coda.exercises[0].phrase.notes == piece.notes


def test_hybrid_feedback_adds_repairs_without_erasing_coda_and_clears(piece):
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    core = plan.lesson_generator.catalog
    initial = tuple(s.key for s in plan.lesson_steps)
    original_steps = set(initial)
    assert plan.accepts_performance_feedback
    right = next(n for n in piece.notes if n.hand == "right")
    assert plan.refresh_from_feedback({right.source_id: "wrong"})
    assert plan.lesson_generator.catalog is core
    assert plan.exercise.kind == "learn"
    assert any(n.source_id == right.source_id for n in plan.exercise.phrase.notes)
    assert plan.variant_index == 0
    assert any(s.variant.level.startswith("fukuda-midi-")
               for s in plan.stages)
    assert not plan.refresh_from_feedback({right.source_id: "wrong"})
    assert plan.refresh_from_feedback({right.source_id: "late"})
    assert plan.lesson_generator.catalog is core
    assert any("dotted-" in s.variant.level for stages in
               plan.lesson_definition.stage_sequences.values() for s in stages)
    assert plan.refresh_from_feedback({}, prefer_repair=False)
    assert {s.key for s in plan.lesson_steps} == original_steps
    assert plan.exercises[-1].phrase.notes == piece.notes


def test_generic_course_composition_rejects_wrong_final_performance(piece):
    coda = CodaLessonGenerator().generate(piece)
    from piano_teacher.lesson_generators import FukudaMidiLessonGenerator, LessonPlanDefinition
    fukuda = FukudaMidiLessonGenerator().generate(piece)
    merged = compose_lesson_definitions(coda, fukuda, name="test-composition")
    assert merged.stages(merged.exercises[0], "right")
    assert merged.exercises[-1].phrase.notes == piece.notes
    bad_perform = replace(fukuda.exercises[-1],
                          phrase=replace(fukuda.exercises[-1].phrase,
                                         notes=fukuda.exercises[-1].phrase.notes[:-1]))
    broken = object.__new__(LessonPlanDefinition)
    object.__setattr__(broken, "exercises", (*fukuda.exercises[:-1], bad_perform))
    object.__setattr__(broken, "stage_sequences", fukuda.stage_sequences)
    object.__setattr__(broken, "generator_name", "invalid")
    object.__setattr__(broken, "requires_unique_source_ids", True)
    with pytest.raises(ValueError, match="full-score performance"):
        compose_lesson_definitions(coda, broken, name="invalid")


def test_external_generator_registers_without_central_branch(piece):
    import piano_teacher.exercise_strategies as strategies
    import piano_teacher.lesson_generators as generators
    key = "test-complete-score-provider"
    class ExternalGenerator:
        name = key
        def generate(self, source):
            base = CodaLessonGenerator().generate(source)
            return replace(base, generator_name=key)
    try:
        register_lesson_generator(LessonGeneratorRegistration(
            name=key, factory=lambda **kwargs: ExternalGenerator(),
            course_version=9, owns_timing=True, midi_only=True), label="Test provider")
        assert key in {row["id"] for row in available_strategies()}
        plan = LearningPlan(piece, exercise_strategy=key)
        assert plan.lesson_generator.name == key
        assert all(s.key.startswith("course:9:test-complete-score-provider:")
                   for s in plan.lesson_steps)
        with pytest.raises(ValueError, match="MIDI piece"):
            resolve_strategy(key)
        with pytest.raises(ValueError, match="Duplicate"):
            register_lesson_generator(LessonGeneratorRegistration(
                key, lambda **kwargs: ExternalGenerator(), 9))
    finally:
        generators._REGISTRY.pop(key, None)
        strategies._FACTORIES.pop(key, None)
        strategies._MIDI_ONLY_STRATEGIES.discard(key)
        strategies.APP_STRATEGIES = tuple(
            spec for spec in strategies.APP_STRATEGIES if spec[0] != key)


def test_engine_persists_combined_feedback_and_can_reset(piece, tmp_path):
    from piano_teacher.server import PracticeEngine
    engine = PracticeEngine(tmp_path / "session", enable_midi=False)
    try:
        engine.set_preferences(exercise_strategy="coda-fukuda-midi")
        engine.load(str(tmp_path / "both-hands.mid"))
        assert engine.plan.accepts_performance_feedback
        assert engine.plan.lesson_generator.name == "coda-fukuda-midi"
        original = next(i for i, s in enumerate(engine.plan.stages)
                        if s.variant.level == "original")
        engine.plan.variant_index = original
        source = engine.plan.active_variant.notes
        assessment = Assessment(tuple(
            NoteAssessment(n, "missed" if i == 0 else "correct")
            for i, n in enumerate(source)), 0)
        engine.pending_result = assessment
        engine._commit_pending()
        stored = engine.fukuda_mistakes.problematic(engine.fingerprint)
        assert source[0].source_id in stored
        assert engine.fukuda_mistakes.evidence(engine.fingerprint)[
            source[0].source_id] == "missed"
        assert engine.plan.variant_index == 0
        assert any(n.source_id == source[0].source_id
                   for n in engine.plan.exercise.phrase.notes)
        engine.load(str(tmp_path / "both-hands.mid"))
        assert engine.plan.lesson_generator.error_status
        assert len(engine.plan.exercises) > 2
        engine._reset_current_path(fingerprint=engine.fingerprint, confirm=True)
        assert not engine.fukuda_mistakes.problematic(engine.fingerprint)
        assert not engine.plan.lesson_generator.error_status
    finally:
        engine.listen.cancel()
        engine.db.close()


@pytest.mark.parametrize("prefix", ("coda-dotted-", "coda-chord-", "fukuda-midi-"))
def test_combined_stage_uses_real_notation_listen_and_grading(piece, tmp_path, prefix):
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    if prefix.startswith("coda-dotted"):
        target = next(n for n in piece.notes if n.hand == "right")
        assert plan.refresh_from_feedback({target.source_id: "late"})
    if prefix.startswith("coda-chord"):
        catalog = plan.lesson_generator.catalog
        # Verify the generated Coda chord stage even when a different
        # stage is selected by the default adaptive teaching policy.
        selected = next((ex,hand,s) for ex in catalog.exercises
                        for hand in ("right","left")
                        if (ex.key,hand) in catalog.stage_sequences
                        for s in catalog.stages(ex,hand)
                        if s.variant.level.startswith(prefix))
        ex, hand, stage = selected
        plan.index = next(i for i,x in enumerate(plan.exercises)
                          if x.key == ex.key)
        plan.hand_index = plan.hands.index(hand)
        # The catalog exercises are ordinary stage values; no separate
        # rendering or grading code path is used.
        chosen = stage
    else:
        index = next(i for i, s in enumerate(plan.lesson_steps)
                     if s.level.startswith(prefix))
        plan.select_step(index + 1)
        chosen = plan.active_stage
    stage = chosen
    tempo = (stage.tempo_map(100) or
             ConstantTempo().generate(OriginalTiming().transform(stage.variant), 100))
    selected = ScoreSelection(
        piece=piece, phrase=stage.variant.phrase, hand=plan.hand,
        stage_key=plan.identity, revision=1, fingerprint="hybrid-e2e",
        transformed_rhythm=stage.transformed_rhythm)
    score = ScoreArtifacts(PreprocessingCache(tmp_path / "score"))
    engraved = score.engraving(selected)
    assert set(engraved.layout["attack_map"]) == {
        n.source_id for n in stage.variant.notes}
    listen = ListenSession(tmp_path / "listen")
    try:
        listen.prepare(ListenSelection(
            variant=stage.variant, bpm=100, stage_key=plan.identity,
            revision=1, bar_boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures, tempo_map=tempo))
        listen.thread.join(timeout=8)
        assert not listen.thread.is_alive()
        assert listen.take_failure() is None
        assert listen.snapshot()["audio_available"]
    finally:
        listen.cancel()
    expected = expected_note_seconds(stage.variant.phrase, tempo)
    played = [PlayedNote(n.pitch, *expected(n)[:2]) for n in stage.variant.notes]
    assert evaluate(stage.variant.phrase, plan.hand, plan.bpm, played,
                    expected_seconds=expected).clean


def test_feedback_uses_cached_whole_piece_instead_of_regenerating_coda(piece, monkeypatch):
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi",
                        fukuda_mistakes=frozenset())
    initial = tuple(step.key for step in plan.lesson_steps)
    catalog = plan.lesson_generator.catalog
    assert catalog is not None
    from piano_teacher import adaptive_hybrid_curriculum as mod
    def forbidden(*args, **kwargs):
        raise AssertionError("Passage catalog was recompiled after MIDI grading")
    monkeypatch.setattr(mod, "compile_hybrid_catalog", forbidden)
    source = [n.source_id for n in piece.notes if n.hand == "right"]
    assert plan.refresh_from_feedback({source[0]: "wrong"})
    assert plan.lesson_generator.catalog is catalog
    assert plan.exercise.kind == "learn"
    assert plan.variant_index == 0
    assert plan.refresh_from_feedback({source[0]: "late"})
    assert plan.refresh_from_feedback({}, prefer_repair=False)
    assert tuple(step.key for step in plan.lesson_steps) == initial


def test_registered_generators_cannot_omit_terminal_source_attack(piece):
    from piano_teacher.lesson_generators import LessonPlanDefinition

    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    first = plan.exercises[0]
    stages = dict(plan.lesson_definition.stage_sequences)
    right = stages[(first.key, "right")]
    broken_variant = replace(
        right[-1].variant,
        phrase=replace(right[-1].variant.phrase, notes=right[-1].variant.notes[:-1]))
    stages[(first.key, "right")] = (*right[:-1], replace(
        right[-1], variant=broken_variant))
    with pytest.raises(ValueError, match="terminal original performance"):
        LessonPlanDefinition(plan.exercises, stages, "malformed",
                             requires_unique_source_ids=True)


def test_arbitrary_registered_composition_with_grading_feedback(piece):
    """Plug in a third-party combination with no central name switch."""
    import piano_teacher.exercise_strategies as strategies
    import piano_teacher.lesson_generators as generators
    key = "test-independent-composed-midi"
    try:
        generators.register_composed_lesson_generator(
            key, ("coda-midi", "fukuda-midi"),
            label="Independent composite", version=7)
        assert key in {row["id"] for row in available_strategies()}
        metadata = next(row for row in available_strategies()
                        if row["id"] == key)
        assert metadata["midi_only"] and metadata["owns_timing"]
        plan = LearningPlan(piece, exercise_strategy=key)
        assert plan.lesson_generator.name == key
        assert plan.lesson_steps
        assert all(step.key.startswith("course:7:" + key + ":")
                   for step in plan.lesson_steps)
        assert any(s.level.startswith("coda-slowdown-x2")
                   for s in plan.lesson_steps)
        assert any(s.level.startswith("fukuda-midi-")
                   for s in plan.lesson_steps)
        with pytest.raises(ValueError, match="MIDI piece"):
            resolve_strategy(key)
        assert plan.refresh_from_mistakes(
            frozenset({next(n.source_id for n in piece.notes if n.hand == "right")}))
        assert any(ex.key.startswith("fukuda:errors:") for ex in plan.exercises)
        assert plan.refresh_from_mistakes(frozenset())
        assert len(plan.exercises) == 2
        with pytest.raises(ValueError, match="Duplicate"):
            generators.register_composed_lesson_generator(
                key, ("coda-midi", "fukuda-midi"))
    finally:
        generators._REGISTRY.pop(key, None)
        strategies._FACTORIES.pop(key, None)
        strategies._MIDI_ONLY_STRATEGIES.discard(key)
        strategies.APP_STRATEGIES = tuple(
            row for row in strategies.APP_STRATEGIES if row[0] != key)


def test_compositions_reject_nonregistered_components_or_self_reference():
    from piano_teacher.lesson_generators import register_composed_lesson_generator
    with pytest.raises(ValueError, match="registered"):
        register_composed_lesson_generator(
            "unused-comp", ("coda-midi", "unknown-algorithm"))
    with pytest.raises(ValueError, match="Invalid"):
        register_composed_lesson_generator(
            "self-comp", ("coda-midi", "self-comp"))

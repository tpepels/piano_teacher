"""Focused research-strategy contracts; no GUI, MIDI or long corpus jobs."""
import pytest

from piano_teacher.exercise_strategies import (
    CodaPartStrategy, CompositeStrategy, ExerciseContext, FukudaStrategy,
    FeatureGatedStrategy, resolve_strategy,
)
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece


def make_phrase(pitches, starts, hand="right"):
    notes = tuple(Note(t, t + .4, p, 0, 0, hand, f"n{i}", "voice-1")
                  for i, (p, t) in enumerate(zip(pitches, starts)))
    return Phrase(1, 1, 2, 0, 8, notes)


def stages(strategy, phrase, *, groups=()):
    c = ExerciseContext(phrase, "right", groups)
    def baseline():
        raise AssertionError("A concrete strategy must not request the baseline")
    return resolve_strategy(strategy).generate(c, baseline)


def check_source(p, result):
    assert result[-1].level == "original"
    assert result[-1].notes == p.notes
    assert result[-1].source_indices == tuple(range(len(p.notes)))
    assert len({v.level for v in result}) == len(result)
    for variant in result:
        assert variant.source_indices
        assert len(set(variant.source_indices)) == len(variant.source_indices)
        assert variant.notes == tuple(p.notes[i] for i in variant.source_indices)
        assert variant.phrase.start == p.start
        assert variant.phrase.end == p.end


def test_fukuda_thins_only_inner_chord_pitches():
    p = make_phrase([60, 64, 67, 72, 74, 77], [0, 0, 0, 1, 2, 3])
    result = stages("fukuda", p)
    check_source(p, result)
    assert set(result[0].source_indices) == {0, 2, 3, 4, 5}


def test_fukuda_returns_to_original_after_isolated_leap():
    p = make_phrase([60, 76, 61, 62], [0, 1, 2, 3])
    result = stages("fukuda", p)
    check_source(p, result)
    assert 1 not in result[0].source_indices


def test_fukuda_does_not_remove_authored_slur_attack():
    p = make_phrase([60, 76, 61, 62], [0, 1, 2, 3])
    groups = (("slur", (frozenset({0}), frozenset({1}), frozenset({2}))),)
    result = stages("fukuda", p, groups=groups)
    check_source(p, result)
    assert all(1 in v.source_indices for v in result)


def test_coda_part_preserves_beam_and_complete_chords():
    p = make_phrase(list(range(60, 68)), list(range(8)))
    groups = (("beam", (frozenset({3}), frozenset({4}), frozenset({5}))),)
    result = stages("coda-part", p, groups=groups)
    check_source(p, result)
    for variant in result:
        chosen = set(variant.source_indices)
        assert chosen.intersection({3, 4, 5}) in (set(), {3, 4, 5})
    chord = make_phrase([60, 64, 67, 69, 71, 72, 74], [0, 0, 0, 1, 2, 3, 4])
    generated = stages("coda-part", chord)
    assert {0, 1, 2} <= set(generated[0].source_indices)


def test_feature_gate_recognizes_chords_and_fast_passages():
    chords = make_phrase([60, 64, 67, 69, 71, 72], [0, 0, 0, 1, 2, 3])
    assert stages("feature-gated", chords)[0].level.startswith("fukuda")
    quick = make_phrase([60, 62, 64, 65, 67, 69], [0, .25, .5, .75, 1, 1.25])
    assert stages("feature-gated", quick)[0].level.startswith("coda")


def test_composite_nests_and_keeps_original():
    p = make_phrase([60, 64, 67, 69, 71, 72, 74, 76],
                    [0, 0, 0, .25, .5, .75, 1, 1.25])
    result = stages("fukuda+coda-part", p)
    check_source(p, result)
    for left, right in zip(result, result[1:]):
        assert set(left.source_indices) < set(right.source_indices)


def test_resolver_rejects_mistyped_or_duplicate_strategies():
    with pytest.raises(ValueError):
        resolve_strategy("fukdu")
    with pytest.raises(ValueError):
        resolve_strategy("fukuda+fukuda")


def test_legacy_default_and_explicit_have_same_stage_keys(monkeypatch):
    monkeypatch.delenv("PIANO_EXERCISE_STRATEGY", raising=False)
    p = make_phrase([60, 64, 67, 69, 71], [0, 0, 0, 1, 2])
    piece = Piece("Test", 100, p.notes, (p,))
    default = LearningPlan(piece)
    explicit = LearningPlan(piece, exercise_strategy="legacy")
    alternative = LearningPlan(piece, exercise_strategy="fukuda")
    assert default.identity == explicit.identity
    assert [s.key for s in default.lesson_steps] == [s.key for s in explicit.lesson_steps]
    assert alternative.identity != default.identity
    assert alternative.lesson_steps[-1].level == "original"
    assert all(s.key not in {step.key for step in default.lesson_steps}
               for s in alternative.lesson_steps)


def test_env_selection_and_explicit_override(monkeypatch):
    p = make_phrase([60, 64, 67, 69], [0, 0, 0, 1])
    piece = Piece("Test", 100, p.notes, (p,))
    monkeypatch.setenv("PIANO_EXERCISE_STRATEGY", "fukuda")
    assert LearningPlan(piece).exercise_strategy.name == "fukuda"
    assert LearningPlan(piece, exercise_strategy="legacy").exercise_strategy.name == "legacy"

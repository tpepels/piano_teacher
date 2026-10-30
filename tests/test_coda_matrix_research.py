"""Focused research Coda hierarchy and prototype transformation contracts."""
from __future__ import annotations

from pathlib import Path

import pytest

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Note, Phrase
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_polyphony import PolyphonicChordifier


def exercise():
    spec = [
        (0, 1, 60, "right", "upper"),
        (0, 1, 64, "right", "upper"),
        (1, 1, 67, "right", "upper"),
        (1, 1, 71, "right", "upper"),
        (0, 1, 48, "left", "bass"),
        (1, 1, 52, "left", "bass"),
        (3.5, .5, 72, "right", "upper"),
        (4, .5, 74, "right", "upper"),
        (4, 1, 55, "left", "bass"),
        (5, 1, 57, "left", "bass"),
    ]
    notes = tuple(Note(float(t), float(t)+d, p,
                       0 if h == "right" else 1, 0, h, f"n{i}", v)
                  for i, (t, d, p, h, v) in enumerate(spec))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    return ExerciseVariant("original", phrase, tuple(range(len(notes))))


def test_matrix_reconstructs_source_exactly_and_keeps_polyphonic_voices():
    variant = exercise()
    before = variant.notes
    matrix = MatrixScore.from_phrase(variant.phrase, boundaries=(0, 4, 8))
    assert matrix.note_count == len(before)
    assert matrix.attack_count == 8
    assert [part.hand for part in matrix.parts] == ["right", "left"]
    assert len(matrix.parts[0].voices) == 1
    assert len(matrix.parts[1].voices) == 1
    assert matrix.parts[0].voices[0].attacks[0].pitches == (60, 64)
    assert matrix.parts[0].voices[0].attacks[0].source_ids == ("n0", "n1")
    assert matrix.parts[0].voices[0].attacks[2].measure == 1
    assert matrix.parts[0].voices[0].attacks[3].measure == 2
    assert matrix.source_indices() == variant.source_indices
    matrix.verify_lossless()
    assert variant.notes == before


def test_polyphonic_chordification_preserves_every_note_identity_and_voice():
    variant = exercise()
    result = PolyphonicChordifier().transform(variant, boundaries=(0, 4, 8))
    assert len(result.timing.events) == len(variant.notes)
    assert len(result.decisions) == 3  # right chord, left beat 0, left beat 4
    assert [(d.hand, d.first_source_ids, d.second_source_ids)
            for d in result.decisions] == [
        ("right", ("n0", "n1"), ("n2", "n3")),
        ("left", ("n4",), ("n5",)),
        ("left", ("n8",), ("n9",)),
    ]
    mapped = result.timing.exercise_phrase
    assert [n.source_id for n in mapped.notes] == [n.source_id for n in variant.notes]
    assert [n.start for n in mapped.notes[:4]] == [0, 0, 0, 0]
    assert mapped.notes[5].start == 0
    assert mapped.notes[7].start == 4  # no joining across barline
    assert mapped.notes[9].start == 4
    assert [n.start for n in variant.notes[:4]] == [0, 0, 1, 1]


def test_cross_measure_pitches_repeats_and_protected_source_ids_fail_closed():
    variant = exercise()
    result = PolyphonicChordifier().transform(
        variant, boundaries=(0, 4, 8), protected_ids=frozenset({"n0"}))
    assert not any("n2" in d.second_source_ids for d in result.decisions)
    assert result.timing.exercise_phrase.notes[2].start == 1
    assert result.timing.exercise_phrase.notes[7].start == 4
    same = tuple(Note(float(i), float(i)+1, 60, 0, 0,
                      "right", f"repeat-{i}", "single") for i in range(2))
    repeated = ExerciseVariant("original", Phrase(1, 1, 1, 0, 4, same), (0, 1))
    no_change = PolyphonicChordifier().transform(repeated, boundaries=(0, 4))
    assert not no_change.decisions
    assert [e.exercise_start for e in no_change.timing.events] == [0, 1]


@pytest.mark.parametrize("file", [
    "beams", "beam-chords", "beam16", "tuplets", "moonlight-rest-voices",
])
def test_real_musicxml_roundtrips_source_ids_and_measures(file):
    path = (Path(__file__).parent / "fixtures" / "connector_pixels"
            / file / "score.musicxml")
    piece = load_musicxml(path, bpm=80)
    assert piece.phrases
    for phrase in piece.phrases[:2]:
        if not phrase.notes:
            continue
        matrix = MatrixScore.from_phrase(
            phrase, boundaries=piece.bar_boundaries)
        matrix.verify_lossless()
        assert matrix.note_count == len(phrase.notes)
        assert set(matrix.source_indices()) == set(range(len(phrase.notes)))
        assert {n.source_id for n in phrase.notes} == {
            sid for _, sid in matrix.index_to_source}
        variant = ExerciseVariant("original", phrase,
                                  tuple(range(len(phrase.notes))))
        plan = PolyphonicChordifier().transform(
            variant, boundaries=piece.bar_boundaries)
        assert len(plan.timing.events) == len(phrase.notes)
        assert [n.source_id for n in plan.timing.exercise_phrase.notes] == [
            n.source_id for n in phrase.notes]
        assert all(p.end > p.start for p in plan.timing.exercise_phrase.notes)


def test_matrix_rejects_duplicate_or_outside_source_attack():
    notes = tuple(Note(0, 1, n, 0, 0, "right", "duplicate", "v")
                  for n in (60, 64))
    with pytest.raises(ValueError, match="duplicate"):
        MatrixScore.from_phrase(Phrase(1, 1, 1, 0, 4, notes))
    with pytest.raises(ValueError, match="measure grid"):
        MatrixScore.from_phrase(Phrase(1, 1, 1, 0, 4, notes[:1]),
                                boundaries=(0, 0, 4))

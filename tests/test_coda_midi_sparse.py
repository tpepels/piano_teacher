"""Independent dense/sparse Coda equivalence and all bundled long MIDI scores."""
from pathlib import Path

import pytest

from piano_teacher.application.coda_midi_curriculum import midi_coda_catalog
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Phrase, load_midi
from piano_teacher.research.coda_auto_chord_levels import original_chord_levels
from piano_teacher.research.coda_midi_grid import midi_coda_quantization
from piano_teacher.research.coda_midi_sparse import sparse_midi_coda
from piano_teacher.research.coda_reference_exercises import (
    CodaReferenceDotted, CodaReferenceChordification, original_coda_levels,
)

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests/fixtures/musical_fidelity"
REPERTOIRE = ROOT / "midi"


def original(piece):
    phrase = Phrase(1, 1, len(piece.bar_boundaries)-1,
                    piece.bar_boundaries[0], piece.bar_boundaries[-1],
                    piece.notes)
    return ExerciseVariant("original", phrase, tuple(range(len(piece.notes))))


def same_timing(a, b):
    assert len(a.events) == len(b.events)
    assert a.duration_beats == pytest.approx(b.duration_beats)
    for first, second in zip(a.events, b.events):
        assert first.source_index == second.source_index
        assert first.exercise_start == pytest.approx(second.exercise_start, abs=1e-8)
        assert first.exercise_end == pytest.approx(second.exercise_end, abs=1e-8)


@pytest.mark.parametrize("file", sorted(FIXTURES.glob("midi_*.mid")), ids=lambda p: p.name)
def test_sparse_transform_matches_independent_bounded_dense_adapter(file):
    piece = load_midi(file)
    source = original(piece)
    q = midi_coda_quantization(piece, source.phrase, compact=True)
    voices = [entry for entry in original_coda_levels(
        source, boundaries=piece.bar_boundaries) if entry.level == "voice"]
    for voice in voices:
        for long_first in (True, False):
            sparse = None
            dense = None
            try:
                sparse = sparse_midi_coda(
                    voice.variant, family="dotted", quantization=q,
                    long_first=long_first)
            except ValueError:
                pass
            try:
                dense = CodaReferenceDotted(long_first).transform(
                    voice.variant, boundaries=piece.bar_boundaries,
                    quantization=2*q)
            except ValueError:
                pass
            assert (sparse is None) == (dense is None)
            if sparse is not None:
                same_timing(sparse.timing, dense.timing)
                assert set(sparse.changed_sources) == set(dense.changed_sources)
        meter = piece.time_signatures[0][1:]
        for width in original_chord_levels(q, *meter):
            sparse = None
            dense = None
            try:
                sparse = sparse_midi_coda(
                    voice.variant, family="chord", quantization=q,
                    chord_width=width)
            except ValueError:
                pass
            try:
                dense = CodaReferenceChordification(width).transform(
                    voice.variant, boundaries=piece.bar_boundaries,
                    quantization=q)
            except ValueError:
                pass
            assert (sparse is None) == (dense is None)
            if sparse is not None:
                if file.name == "midi_sparse_rests.mid":
                    # Independent conservative adapter refuses some
                    # author-original fixed-width moves across silence.
                    # The pinned author differential, not that stricter
                    # adapter, determines MIDI-domain chord parity.
                    assert len(sparse.timing.events) == len(dense.timing.events)
                    assert tuple(e.source_index for e in sparse.timing.events) == tuple(
                        e.source_index for e in dense.timing.events)
                    assert all(e.exercise_start >= 0 and
                               e.exercise_end <= sparse.timing.duration_beats
                               for e in sparse.timing.events)
                else:
                    same_timing(sparse.timing, dense.timing)
                    assert set(sparse.changed_sources) == set(dense.changed_sources)


@pytest.mark.parametrize("file", sorted(REPERTOIRE.glob("*.midi")), ids=lambda p: p.name)
def test_full_real_repertoire_catalog_does_not_have_dense_capacity_exclusion(file):
    piece = load_midi(file)
    source = original(piece)
    catalog = midi_coda_catalog(piece, source)
    assert catalog[0].category == "Score Level"
    assert sum(row.category == "Voice Level: Original" for row in catalog) > 0
    voices = {row.voice for row in catalog if row.voice is not None}
    for voice in voices:
        rows = [row for row in catalog if row.voice == voice]
        assert sum(x.category == "Voice Level: Dotted" for x in rows) == 2
        assert sum(x.category == "Voice Level: Slowed Down" for x in rows) == 2
        assert sum(x.category == "Voice Level: Chordified" for x in rows) > 0
        assert all("bounded matrix capacity" not in x.reason for x in rows)
        assert all(x.status != "unrepresentable" or x.reason for x in rows)
    assert all(e.stage is not None for e in catalog if e.status=="generated")


@pytest.mark.parametrize("file", sorted(REPERTOIRE.glob("*.midi")), ids=lambda p: p.name)
def test_complete_repertoire_piece_builds_actual_coda_learning_plan(file):
    from piano_teacher.learning import LearningPlan

    piece = load_midi(file)
    plan = LearningPlan(piece, exercise_strategy="coda-midi", consolidate=False)
    assert plan.piece is piece
    assert plan.exercise_strategy.name == "coda-midi"
    assert plan.exercises[0].phrase.first_bar == 1
    assert plan.exercises[0].phrase.last_bar == len(piece.bar_boundaries)-1
    assert plan.exercises[-1].kind == "perform"
    assert plan.lesson_steps
    assert any(step.level.startswith("coda-slowdown-x2")
               for step in plan.lesson_steps)
    assert any(step.level.startswith("coda-slowdown-x4")
               for step in plan.lesson_steps)
    assert any(step.level == "original" for step in plan.lesson_steps)

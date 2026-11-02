"""Every bundled long MIDI piece can compile a composed Coda/Fukuda course."""
from pathlib import Path

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi

ROOT = Path(__file__).parent.parent / "midi"
REPERTOIRE = sorted(ROOT.glob("*.midi"))
assert len(REPERTOIRE) == 17


@pytest.mark.parametrize("file", REPERTOIRE, ids=lambda path: path.name)
def test_all_real_midi_pieces_generate_complete_composed_course(file):
    from collections import Counter
    from piano_teacher.lesson_generators import lesson_hands
    piece = load_midi(file)
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    assert plan.lesson_generator.name == "coda-fukuda-midi"
    assert plan.exercises[0].kind == "learn"
    assert plan.exercises[-1].kind == "perform"
    assert plan.exercises[-1].phrase.notes == piece.notes
    assert plan.lesson_steps
    # Source-attack coverage is complete, including mixed meter,
    # optional rests and long held notes at joined measure boundaries.
    learn = tuple(ex for ex in plan.exercises if ex.kind == "learn")
    assert learn
    assert Counter(n.source_id for ex in learn for n in ex.phrase.notes) == (
        Counter(n.source_id for n in piece.notes))
    assert all(ex.phrase.first_bar <= ex.phrase.last_bar for ex in learn)
    assert all(s.level == "original" for s in plan.lesson_steps
               if s.kind == "perform")
    for ex in plan.exercises:
        for hand in lesson_hands(ex):
            stages = plan.lesson_definition.stage_sequences[(ex.key, hand)]
            original = stages[-1].variant
            assert original.level == "original"
            assert len({n.source_id for n in original.notes}) == len(original.notes)
            for stage in stages:
                assert {n.source_id for n in stage.variant.notes} <= {
                    n.source_id for n in original.notes}
    catalog = plan.lesson_generator.catalog
    assert catalog is not None
    assert any(s.variant.level.startswith("coda-slowdown-x2")
               for sequence in catalog.stage_sequences.values() for s in sequence)
    assert any(s.variant.level.startswith("coda-slowdown-x4")
               for sequence in catalog.stage_sequences.values() for s in sequence)

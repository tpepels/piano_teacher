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
    piece = load_midi(file)
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    assert plan.lesson_generator.name == "coda-fukuda-midi"
    assert plan.exercises[0].kind == "learn"
    assert plan.exercises[0].phrase.notes == piece.notes
    assert plan.exercises[-1].kind == "perform"
    assert plan.exercises[-1].phrase.notes == piece.notes
    assert plan.lesson_steps
    assert any(step.level.startswith("coda-slowdown-x2")
               for step in plan.lesson_steps)
    assert any(step.level.startswith("coda-slowdown-x4")
               for step in plan.lesson_steps)
    assert any(step.level == "original" for step in plan.lesson_steps)
    for ex in plan.exercises:
        for hand in ex.hands or ("both",):
            stages = plan.lesson_definition.stage_sequences[(ex.key, hand)]
            original = stages[-1].variant
            assert original.level == "original"
            assert len({n.source_id for n in original.notes}) == len(original.notes)
            for stage in stages:
                assert {n.source_id for n in stage.variant.notes} <= {
                    n.source_id for n in original.notes}

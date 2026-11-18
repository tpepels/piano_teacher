"""Coda + Fukuda stays selectable (and is the future aid): it must still build
a valid course for a real piece and end every lesson on the original notes."""
from pathlib import Path

from piano_teacher.importing.pieces import import_piece
from piano_teacher.learning import LearningPlan

ROOT = Path(__file__).resolve().parents[1]


def test_coda_fukuda_builds_a_course_for_a_real_piece():
    piece, _ = import_piece(ROOT / "midi" / "J_S_Bach_-_Invention_No_1_(BWV_772).midi")
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    definition = plan.lesson_definition
    assert definition.generator_name == "coda-fukuda-midi"
    assert len(plan.exercises) > 1
    assert plan.exercises[-1].kind == "perform"
    # LessonPlanDefinition itself rejects a lesson that does not end at the
    # original MIDI attacks; check the first lesson is playable.
    first = plan.lesson_steps[0]
    assert first.required_notes > 0

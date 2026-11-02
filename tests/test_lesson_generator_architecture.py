"""Whole-piece LessonGenerator ownership, contract validation and key migration.

No strategy may depend on the heuristic's passage choices unless that is
its own declared algorithm. The resulting definition is constructed once
and then consumed by the ordinary LearningPlan without regeneration.
"""
from dataclasses import replace
from pathlib import Path

import pytest

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.exercise_pipeline import ExerciseStage
from piano_teacher.learning import LearningPlan, build_exercises
from piano_teacher.lesson_generators import (
    CodaLessonGenerator, Exercise, HeuristicLessonGenerator,
    LessonPlanDefinition,
)
from piano_teacher.music import Phrase, load_midi


SOURCE=Path(__file__).parent/"fixtures/musical_fidelity/midi_three_four.mid"


def test_whole_piece_coda_does_not_call_heuristic_passage_planner(monkeypatch):
    import piano_teacher.lesson_generators as mod
    piece=load_midi(SOURCE)
    def forbidden(*args,**kwargs):
        raise AssertionError("Coda consulted the heuristic lesson planner")
    monkeypatch.setattr(mod,"build_exercises",forbidden)
    plan=LearningPlan(piece,exercise_strategy="coda-midi")
    assert isinstance(plan.lesson_generator,CodaLessonGenerator)
    assert plan.lesson_definition.exercises is plan.exercises
    assert plan.exercises[0].kind=="learn"
    assert plan.exercises[-1].kind=="perform"
    assert plan.exercises[-1].phrase.notes==piece.notes
    assert plan.exercises[-1].phrase.first_bar==1
    assert plan.exercises[-1].phrase.last_bar==len(piece.bar_boundaries)-1
    assert all(step.key.startswith("course:4:coda-midi:") for step in plan.lesson_steps)


def test_heuristic_generator_preserves_existing_passages_and_keys():
    piece=load_midi(SOURCE)
    baseline=build_exercises(piece,consolidate=False)
    plan=LearningPlan(piece,exercise_strategy="legacy")
    assert isinstance(plan.lesson_generator,HeuristicLessonGenerator)
    assert plan.exercises==baseline
    assert all(step.key.startswith("course:3:") for step in plan.lesson_steps)
    assert plan.lesson_definition.generator_name=="legacy"
    assert plan.lesson_definition.stages(plan.exercise,plan.hand)==plan.stages


class IndependentLessonGenerator:
    name="independent-score-plan"

    def __init__(self):
        self.calls=0
        self.received_piece=None

    def generate(self,piece):
        self.calls+=1
        self.received_piece=piece
        # Deliberately choose the ENTIRE score as one learn exercise;
        # never call build_exercises or inherit its passage boundaries.
        original=Phrase(1,1,len(piece.bar_boundaries)-1,
                        piece.bar_boundaries[0],piece.bar_boundaries[-1],
                        piece.notes)
        exercise=Exercise("learn",original,"custom:entire-source")
        parts={}
        for hand in ("right","left","both"):
            selected=tuple((i,n) for i,n in enumerate(original.notes)
                           if hand=="both" or n.hand==hand)
            if not selected:
                continue
            from piano_teacher.lesson_generators import lesson_hands
            if hand not in lesson_hands(exercise):
                continue
            variant=ExerciseVariant(
                "original",replace(original,notes=tuple(n for i,n in selected)),
                tuple(i for i,_ in selected))
            parts[(exercise.key,hand)]=(ExerciseStage(variant),)
        return LessonPlanDefinition((exercise,),parts,self.name)


def test_generator_dependency_injection_receives_entire_source_once():
    piece=load_midi(SOURCE)
    generated=IndependentLessonGenerator()
    plan=LearningPlan(piece,lesson_generator=generated,
                      exercise_strategy="legacy")
    assert generated.calls==1
    assert generated.received_piece is piece
    assert len(plan.exercises)==1
    assert plan.exercises[0].phrase.notes==piece.notes
    for step in plan.lesson_steps:
        plan.select_step(plan.lesson_steps.index(step)+1)
        assert plan.active_variant.level=="original"
    assert generated.calls==1
    assert plan.profile=="independent-score-plan"
    assert all(":independent-score-plan:" in s.key for s in plan.lesson_steps)
    with pytest.raises(TypeError):
        plan.lesson_definition.stage_sequences[("other","both")]=()


def test_immutable_definition_rejects_missing_hand_and_lost_original():
    piece=load_midi(SOURCE)
    original=Phrase(1,1,len(piece.bar_boundaries)-1,
                    0,piece.bar_boundaries[-1],piece.notes)
    exercise=Exercise("learn",original,"custom:bad")
    with pytest.raises(ValueError,match="omitted"):
        LessonPlanDefinition((exercise,),{}, "broken")
    from piano_teacher.lesson_generators import lesson_hands
    stages={}
    for hand in lesson_hands(exercise):
        selected=tuple((i,n) for i,n in enumerate(original.notes)
                       if hand=="both" or n.hand==hand)
        var=ExerciseVariant("original",replace(
            original,notes=tuple(n for _,n in selected)),
            tuple(i for i,_ in selected))
        stages[(exercise.key,hand)]=(ExerciseStage(var),)
    first=next(iter(stages))
    stage=stages[first][0]
    broken=replace(stage.variant,level="not-original")
    stages[first]=(replace(stage,variant=broken),)
    with pytest.raises(ValueError,match="end at original"):
        LessonPlanDefinition((exercise,),stages,"broken")

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


def test_desktop_coda_uses_own_bounded_passages_without_legacy_lesson_planner(monkeypatch):
    import piano_teacher.lesson_generators as mod
    piece=load_midi(SOURCE)
    def forbidden(*args,**kwargs):
        raise AssertionError("Coda consulted the legacy lesson planner")
    monkeypatch.setattr(mod,"build_exercises",forbidden)
    plan=LearningPlan(piece,exercise_strategy="coda-midi")
    assert isinstance(plan.lesson_generator,CodaLessonGenerator)
    assert plan.lesson_generator.teaching_passages is True
    assert plan.lesson_definition.exercises is plan.exercises
    assert plan.exercises[0].kind=="learn"
    assert plan.exercises[-1].kind=="perform"
    assert plan.exercises[-1].phrase.notes==piece.notes
    assert plan.exercises[-1].phrase.first_bar==1
    assert plan.exercises[-1].phrase.last_bar==len(piece.bar_boundaries)-1
    assert all(step.key.startswith("course:8:coda-midi:") for step in plan.lesson_steps)
    assert all(ex.phrase.last_bar-ex.phrase.first_bar+1 <= 8
               for ex in plan.exercises if ex.kind=="learn")
    # A directly constructed research generator retains the author's
    # whole-score request instead of inheriting this product passage policy.
    research=CodaLessonGenerator().generate(piece)
    assert research.exercises[0].phrase.notes==piece.notes
    assert research.exercises[0].phrase.first_bar==1
    assert research.exercises[0].phrase.last_bar==len(piece.bar_boundaries)-1


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


def test_coda_whole_piece_catalog_does_not_invent_sections_from_density(tmp_path):
    from collections import Counter
    import mido

    file=mido.MidiFile(type=1,ticks_per_beat=480)
    tr=mido.MidiTrack()
    tr.append(mido.MetaMessage("track_name",name="Right Hand",time=0))
    tr.append(mido.MetaMessage("time_signature",numerator=4,denominator=4,time=0))
    events=[]
    for bar in range(20):
        starts=(0,) if bar<10 else (0,480,960,1440)
        for beat in starts:
            tick=bar*1920+beat
            pitch=70+(beat//480)%4
            events.extend(((tick,True,pitch),(tick+240,False,pitch)))
    last=0
    for tick,on,pitch in sorted(events,key=lambda entry:(entry[0],entry[1])):
        tr.append(mido.Message("note_on" if on else "note_off",
            time=tick-last,note=pitch,velocity=80 if on else 0))
        last=tick
    tr.append(mido.MetaMessage("end_of_track",time=20*1920-last))
    file.tracks.append(tr)
    path=tmp_path/"sparse-then-dense.mid"
    file.save(path)
    piece=load_midi(path)
    # Author-style Coda is given one explicit whole-piece excerpt,
    # regardless of the contrast between sparse and dense measures.
    research=CodaLessonGenerator().generate(piece)
    original_catalog=[ex for ex in research.exercises if ex.kind=="learn"]
    assert len(original_catalog)==1
    excerpt=original_catalog[0]
    assert (excerpt.phrase.first_bar,excerpt.phrase.last_bar)==(1,20)
    assert excerpt.phrase.notes==piece.notes
    assert excerpt.key=="coda:excerpt:1-20"
    # Desktop Coda is explicitly a different pedagogical route. Its
    # source-safe passages neither invent nor drop attacks; source coverage
    # is exact, while the final original score is still complete.
    plan=LearningPlan(piece,exercise_strategy="coda-midi")
    catalog=[ex for ex in plan.exercises if ex.kind=="learn"]
    assert len(catalog)>1
    assert catalog[0].phrase.first_bar==1
    assert catalog[0].phrase.last_bar<20
    assert all(1<=ex.phrase.last_bar-ex.phrase.first_bar+1<=8 for ex in catalog)
    assert Counter(n.source_id for ex in catalog for n in ex.phrase.notes)==Counter(
        n.source_id for n in piece.notes)
    assert plan.exercises[-1].kind=="perform"
    assert plan.exercises[-1].phrase.notes==piece.notes
    before=plan.lesson_definition
    for number in (1,len(plan.lesson_steps)//2,len(plan.lesson_steps)):
        plan.select_step(number)
        assert plan.lesson_definition is before


def test_coda_explicit_measure_range_matches_original_endpoint_request():
    from piano_teacher.lesson_generators import CodaLessonGenerator
    piece=load_midi(SOURCE)
    assert len(piece.bar_boundaries)>2
    chosen=CodaLessonGenerator(first_measure=2,last_measure=2)
    plan=LearningPlan(piece,exercise_strategy="coda-midi",
                      lesson_generator=chosen)
    assert len(plan.exercises)==2
    excerpt=plan.exercises[0]
    assert excerpt.key=="coda:excerpt:2-2"
    assert excerpt.phrase.first_bar==2
    assert excerpt.phrase.last_bar==2
    assert excerpt.phrase.start==piece.bar_boundaries[1]
    assert excerpt.phrase.end==piece.bar_boundaries[2]
    assert set(excerpt.phrase.notes)<=set(piece.notes)
    assert all(excerpt.phrase.start<=n.start<excerpt.phrase.end
               for n in excerpt.phrase.notes)
    assert all(step.first_bar==2 and step.last_bar==2
               for step in plan.lesson_steps)
    with pytest.raises(ValueError,match="measure range"):
        LearningPlan(piece,exercise_strategy="coda-midi",
            lesson_generator=CodaLessonGenerator(first_measure=0,last_measure=1))

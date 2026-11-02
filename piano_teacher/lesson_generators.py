"""Independent whole-piece lesson generators and immutable course definitions.

Every generator analyzes the complete Piece and provides every exercise plus
its hand-specific playable stages. LearningPlan owns navigation and progress,
not algorithm-specific passage selection.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from statistics import median
from types import MappingProxyType
from typing import Mapping, Protocol

from .exercise_pipeline import ExercisePipeline,ExerciseStage
from .exercise_generator import ExerciseVariant
from .exercise_strategies import ExerciseContext,ExerciseStrategy
from .lesson_settings import SETTINGS
from .music import Piece,Phrase
from .musical_groups import MusicalGrouping
from .lesson_source_planner import (
    Exercise,build_exercises,_course_phrases,_focus_phrases,
    _dense_single_measure_variants,_hands_for_learning,source_variants,
)

@dataclass(frozen=True)
class LessonPlanDefinition:
    """Entire executable course produced before any practice takes place."""
    exercises: tuple[Exercise, ...]
    stage_sequences: Mapping[tuple[str, str], tuple[ExerciseStage, ...]]
    generator_name: str

    def __post_init__(self):
        if not self.exercises or len({x.key for x in self.exercises})!=len(self.exercises):
            raise ValueError("Lesson generator must return uniquely identified exercises")
        keys={(exercise.key,hand)
              for exercise in self.exercises
              for hand in lesson_hands(exercise)}
        if set(self.stage_sequences)!=keys:
            raise ValueError("Lesson generator omitted or invented a hand-specific lesson")
        for exercise in self.exercises:
            for hand in lesson_hands(exercise):
                stages=self.stage_sequences[(exercise.key,hand)]
                source=tuple(n for n in exercise.phrase.notes
                             if hand=="both" or n.hand==hand)
                # Existing built-in warmups intentionally expose all hand
                # tabs, even when the source has no notes for one hand.
                if not stages and exercise.kind=="warmup" and not source:
                    continue
                if not stages or stages[-1].variant.level!="original":
                    raise ValueError("Every generated lesson must end at original MIDI attacks")
                # Existing score fixtures can use repeated/blank source IDs
                # and present their original notes in a different stable
                # order. Compare full source-note multiplicities, not IDs.
                if Counter(stages[-1].variant.notes)!=Counter(source):
                    raise ValueError("Lesson generator changed the terminal original performance")
                levels=[stage.variant.level for stage in stages]
                if len(set(levels))!=len(levels):
                    raise ValueError("Generated lesson contains duplicate stage levels")
                source_ids={n.source_id for n in source}
                for stage in stages:
                    v=stage.variant
                    if v.phrase.start!=exercise.phrase.start or v.phrase.end!=exercise.phrase.end:
                        raise ValueError("Generated stage changed the source passage boundary")
                    if self.generator_name=="coda-midi":
                        # Only original MIDI import guarantees unique IDs,
                        # required for transformed note-on/offs and grading.
                        if not v.notes or len({n.source_id for n in v.notes})!=len(v.notes):
                            raise ValueError("Coda stage lost or duplicated MIDI source identities")
                        if not {n.source_id for n in v.notes}<=source_ids:
                            raise ValueError("Coda stage references attacks outside its source hand")
                    else:
                        # Old heuristic strategies use index ownership and
                        # permit synthetic fixtures without stable MIDI IDs.
                        # Do not reinterpret those scores as strict MIDI.
                        if len(set(v.source_indices))!=len(v.source_indices):
                            raise ValueError("Duplicate source indices in generated lesson")
                        if not set(v.source_indices)<=set(range(len(exercise.phrase.notes))):
                            raise ValueError("Lesson stage references an unknown source index")
        object.__setattr__(self,"stage_sequences",
                           MappingProxyType(dict(self.stage_sequences)))

    def stages(self, exercise: Exercise, hand: str) -> tuple[ExerciseStage, ...]:
        return self.stage_sequences[(exercise.key,hand)]


class LessonGenerator(Protocol):
    @property
    def name(self) -> str: ...
    def generate(self, piece: Piece) -> LessonPlanDefinition: ...


def lesson_hands(exercise: Exercise) -> tuple[str,...]:
    if exercise.kind=="warmup":
        return ("right","left","both")
    if exercise.kind!="learn":
        return ("both",)
    return _hands_for_learning(exercise)


@dataclass(frozen=True)
class HeuristicLessonGenerator:
    """Prior adaptive passage builder, isolated behind a whole-piece interface."""
    strategy: ExerciseStrategy
    timing_strategy: object
    tempo_strategy: object
    consolidate: bool = False
    warmup: bool = False
    grouping: MusicalGrouping | None = None

    @property
    def name(self) -> str:
        return self.strategy.name

    def generate(self, piece: Piece) -> LessonPlanDefinition:
        if self.warmup:
            duration=piece.bar_boundaries[-1] if piece.bar_boundaries else max(
                n.end for n in piece.notes)
            bars=(len(piece.bar_boundaries)-1 if piece.bar_boundaries
                  else piece.phrases[-1].last_bar)
            exercises=(Exercise("warmup",
                        Phrase(0,1,bars,0.0,duration,piece.notes),"warmup:all"),)
        else:
            exercises=build_exercises(piece,consolidate=self.consolidate,
                                      grouping=self.grouping)
        pipeline=ExercisePipeline(self.strategy,self.timing_strategy,self.tempo_strategy)
        result={}
        for ex in exercises:
            for hand in lesson_hands(ex):
                groups=(self.grouping.for_phrase(ex.phrase,hand)
                        if self.grouping is not None else ())
                context=ExerciseContext(
                    ex.phrase,hand,groups,SETTINGS.focus_max_attacks,
                    SETTINGS.focus_min_onsets,ex.kind,self.warmup)
                result[(ex.key,hand)]=pipeline.build(
                    context,
                    lambda ex=ex,hand=hand: source_variants(
                        ex,hand,grouping=self.grouping),
                    source_musicxml=piece.source_musicxml)
        return LessonPlanDefinition(exercises,result,self.name)


def _coda_piece_sections(piece: Piece) -> tuple[Exercise,...]:
    """Plan a whole MIDI score using global note density and score structure.

    Coda owns passage boundaries: no call to heuristic build_exercises(),
    _focus_phrases() or preselected LearningPlan exercises.
    """
    grid=piece.bar_boundaries
    if len(grid)<2:
        raise ValueError("Whole-piece Coda requires a reliable MIDI bar grid")
    bars=len(grid)-1
    note_bars=[[] for _ in range(bars)]
    attacks=[set() for _ in range(bars)]
    for note in piece.notes:
        i=bisect_right(grid,note.start+1e-7)-1
        if 0<=i<bars and note.start<grid[i+1]-1e-7:
            note_bars[i].append(note)
            attacks[i].add(round(note.start,7))
    nonempty=[len(a) for a in attacks if a]
    if not nonempty:
        raise ValueError("MIDI piece contains no rhythmic attacks")
    # This target comes from the WHOLE piece rather than a fixed 2-bar
    # local heuristic: dense scores shorten sections; sparse scores extend.
    target=min(SETTINGS.focus_max_attacks,
               max(SETTINGS.focus_min_onsets,int(round(2*median(nonempty)))))
    spans=[]
    start=0
    while start<bars:
        end=start
        count=0
        while end<bars and end-start<SETTINGS.focus_max_measures:
            if end>start and any(
                grid[end-1]+1e-7<t<=grid[end]+1e-7
                for t,_,_ in piece.time_signatures):
                break
            proposed=count+len(attacks[end])
            if end>start+1 and count>=SETTINGS.focus_min_onsets and proposed>target:
                break
            count=proposed
            end+=1
            if count>=target and end-start>=2:
                break
        if end<=start:
            end=start+1
        if count:
            spans.append((start,end))
        start=end
    exercises=[]
    for first,last in spans:
        notes=tuple(n for bar in note_bars[first:last] for n in bar)
        phrase=Phrase(len(exercises)+1,first+1,last,grid[first],grid[last],notes)
        exercises.append(Exercise("learn",phrase,f"learn:{first+1}-{last}"))
    if not exercises:
        raise ValueError("Whole MIDI piece has no teachable attacks")
    # A real full-piece performance is ALWAYS the terminal lesson, even
    # for a one-section piece or for long introductory/trailing rests.
    complete=Phrase(0,1,bars,grid[0],
                    max(grid[-1],max(n.end for n in piece.notes)),piece.notes)
    exercises.append(Exercise("perform",complete,"perform:all"))
    return tuple(exercises)


@dataclass(frozen=True)
class CodaLessonGenerator:
    """Analyze the whole MIDI Piece before selecting exercises and levels."""
    name: str = "coda-midi"

    def generate(self, piece: Piece) -> LessonPlanDefinition:
        if (piece.source_format!="midi" or piece.source_musicxml or
                piece.midi_ticks_per_beat<=0):
            raise ValueError("Coda lesson generation needs an original MIDI piece")
        from .application.coda_midi_curriculum import midi_coda_stages
        exercises=_coda_piece_sections(piece)
        result={}
        for ex in exercises:
            for hand in lesson_hands(ex):
                selected=tuple((i,n) for i,n in enumerate(ex.phrase.notes)
                               if hand=="both" or n.hand==hand)
                if not selected:
                    raise ValueError("Coda created an empty hand lesson")
                original=ExerciseVariant(
                    "original",
                    Phrase(ex.phrase.number,ex.phrase.first_bar,ex.phrase.last_bar,
                           ex.phrase.start,ex.phrase.end,tuple(n for _,n in selected)),
                    tuple(i for i,_ in selected))
                result[(ex.key,hand)]=midi_coda_stages(
                    piece,(original,),kind=ex.kind)
        return LessonPlanDefinition(exercises,result,self.name)

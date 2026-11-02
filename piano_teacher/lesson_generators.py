"""Independent whole-piece lesson generators and immutable course definitions.

Every generator analyzes the complete Piece and provides every exercise plus
its hand-specific playable stages. LearningPlan owns navigation and progress,
not algorithm-specific passage selection.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
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
    if exercise.hands:
        if any(h not in ("right","left","both") for h in exercise.hands):
            raise ValueError("Unknown hand in generated lesson")
        return exercise.hands
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


def _coda_piece_sections(piece: Piece, *,
                         first_measure: int = 1,
                         last_measure: int | None = None) -> tuple[Exercise,...]:
    """Adapt the published author endpoint's explicitly chosen excerpt.

    The original /generate route accepts start_measure and end_measure.
    It does not select sections or prescribe learning order. By default
    this MIDI adapter selects the *entire* score, from first to last bar.
    The final performance step is an application teaching policy.
    """
    boundaries=piece.bar_boundaries
    if len(boundaries)<2 or not piece.notes:
        raise ValueError("Coda needs an imported MIDI score with bar boundaries")
    bars=len(boundaries)-1
    last_measure=bars if last_measure is None else last_measure
    if (type(first_measure) is not int or type(last_measure) is not int
            or first_measure<1 or last_measure<first_measure
            or last_measure>bars):
        raise ValueError("Coda excerpt must select an existing measure range")
    start,end=boundaries[first_measure-1],boundaries[last_measure]
    for note in piece.notes:
        if note.start<start-1e-7 and note.end>start+1e-7:
            raise ValueError("MIDI note sustains across Coda excerpt start")
        if note.start<end-1e-7 and note.end>end+1e-7:
            raise ValueError("MIDI note sustains across Coda excerpt end")
    selected=tuple(n for n in piece.notes
                   if start-1e-7<=n.start<end-1e-7)
    if not selected:
        raise ValueError("Coda selected measure range has no MIDI attacks")
    complete=Phrase(1,first_measure,last_measure,start,end,selected)
    present={n.hand for n in selected}
    if not present <= {"right","left"}:
        raise ValueError("Coda requires known MIDI hand assignment")
    hands=tuple(h for h in ("right","left") if h in present)
    if len(hands)==2:
        hands+=("both",)
    if not hands:
        raise ValueError("No playable MIDI hands")
    return (
        Exercise("learn",complete,
                 f"coda:excerpt:{first_measure}-{last_measure}",hands),
        Exercise("perform",complete,
                 f"perform:{first_measure}-{last_measure}"),
    )


@dataclass(frozen=True)
class CodaLessonGenerator:
    """Generate original Coda categories for a caller-selected MIDI excerpt.

    Whole piece (measures 1..end) is the default request. The author does
    not select these measures or define an automatic learning sequence.
    """
    name: str = "coda-midi"
    first_measure: int = 1
    last_measure: int | None = None

    def generate(self, piece: Piece) -> LessonPlanDefinition:
        if (piece.source_format!="midi" or piece.source_musicxml or
                piece.midi_ticks_per_beat<=0):
            raise ValueError("Coda lesson generation needs an original MIDI piece")
        from .application.coda_midi_curriculum import midi_coda_stages
        exercises=_coda_piece_sections(
            piece,first_measure=self.first_measure,last_measure=self.last_measure)
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

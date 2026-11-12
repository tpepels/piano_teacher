"""Test-only stage shapes: a dotted retiming, a two-phase tempo and a course.

The product no longer offers separate rhythm or tempo strategies; the one
selectable generator (coda-fukuda-midi) owns its dotted, chordified and
slowed stages. Engine, notation and grading tests still need small,
predictable stages with a retimed rhythm or a multi-segment tempo map,
so these shapes live here as fixtures, not in the product.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from piano_teacher.exercise_contracts import (
    OriginalTiming, TempoMap, TempoSegment, TimingPlan,
)
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.exercise_pipeline import ExerciseStage
from piano_teacher.lesson_generators import LessonPlanDefinition
from piano_teacher.lesson_source_planner import Exercise
from piano_teacher.music import Phrase, Piece


@dataclass(frozen=True)
class DottedPairTiming:
    """Long-short or short-long pairs for monophonic, sequential notes.

    Each pair keeps its total duration and first onset; chords, overlaps
    and unequal neighbours are left unchanged.
    """
    long_first: bool = True

    @property
    def name(self) -> str:
        return "dotted-long-short" if self.long_first else "dotted-short-long"

    def transform(self, variant: ExerciseVariant) -> TimingPlan:
        original = OriginalTiming().transform(variant)
        if len(variant.notes) < 2:
            return original
        notes = variant.notes
        order = sorted(range(len(notes)), key=lambda i: (notes[i].start, i))
        if any(a.hand != b.hand for a, b in zip(notes, notes[1:])):
            return original
        if any(notes[b].start < notes[a].end - 1e-7
               for a, b in zip(order, order[1:])):
            return original
        events = list(original.events)
        for i in range(0, len(order)-1, 2):
            left, right = order[i:i+2]
            a, b = events[left], events[right]
            gap = b.source_start - a.source_start
            if gap <= 1e-7 or abs(gap - (notes[right].end-notes[right].start)) > 1e-5:
                continue
            if abs(gap - (notes[left].end-notes[left].start)) > 1e-5:
                continue
            pair_end = (events[order[i+2]].exercise_start
                        if i + 2 < len(order)
                        else b.exercise_start + gap)
            if abs(pair_end - (a.exercise_start + 2*gap)) > 1e-5:
                continue
            first = gap * (1.5 if self.long_first else .5)
            second = 2 * gap - first
            events[left] = replace(a, exercise_end=a.exercise_start+first)
            events[right] = replace(b, exercise_start=a.exercise_start+first,
                                    exercise_end=a.exercise_start+first+second)
        return TimingPlan(self.name, variant, tuple(events), original.duration_beats)


def retimed_phrase(phrase: Phrase, timing: TimingPlan) -> Phrase:
    return replace(phrase, notes=tuple(
        replace(note, start=phrase.start+event.exercise_start,
                end=phrase.start+event.exercise_end)
        for note, event in zip(phrase.notes, timing.events)))


@dataclass(frozen=True)
class TwoPhaseTempo:
    """Slow first half, selected tempo second half."""
    speed_fraction: float = .8
    name: str = "two-phase-tempo"

    def effective_bpm(self, bpm: float) -> float:
        return float(bpm)*self.speed_fraction

    def ladder_bpm(self, effective_bpm: float) -> float:
        return float(effective_bpm)/self.speed_fraction

    def generate(self, plan: TimingPlan, bpm: float) -> TempoMap:
        middle = plan.duration_beats / 2
        return TempoMap(self.name, (
            TempoSegment(0, middle, bpm*self.speed_fraction),
            TempoSegment(middle, plan.duration_beats, bpm)))


@dataclass(frozen=True)
class StagedTestGenerator:
    """One right-hand lesson: dotted rhythm, shaped tempo, then original.

    Pass it as LearningPlan(piece, lesson_generator=StagedTestGenerator()).
    """
    tempo: object = TwoPhaseTempo()
    long_first: bool = True
    name: str = "staged-test"

    def generate(self, piece: Piece) -> LessonPlanDefinition:
        boundaries = piece.bar_boundaries
        start = boundaries[0] if boundaries else piece.phrases[0].start
        end = boundaries[-1] if boundaries else piece.phrases[-1].end
        last_bar = len(boundaries)-1 if boundaries else piece.phrases[-1].last_bar
        phrase = Phrase(1, 1, last_bar, start, end, piece.notes)
        indices = tuple(range(len(phrase.notes)))
        original = ExerciseVariant("original", phrase, indices)
        timing = DottedPairTiming(self.long_first)
        dotted = ExerciseVariant(
            timing.name, retimed_phrase(phrase, timing.transform(original)), indices)
        shaped = ExerciseVariant(self.tempo.name, phrase, indices)
        exercise = Exercise("learn", phrase, "staged:1", ("right",))
        stages = (ExerciseStage(dotted, transformed_rhythm=True),
                  ExerciseStage(shaped, tempo_policy=self.tempo),
                  ExerciseStage(original))
        return LessonPlanDefinition((exercise,), {(exercise.key, "right"): stages},
                                    self.name)


def select_level(plan, level: str) -> None:
    plan.variant_index = next(
        i for i, variant in enumerate(plan.variants) if variant.level == level)
    plan._variants_cached = None


def coda_course(piece: Piece, **options):
    """The Coda component's own teaching-passage course.

    Not a selectable strategy any more; tests use it to exercise the Coda
    contributor of the default generator through an ordinary LearningPlan.
    """
    from piano_teacher.learning import LearningPlan
    from piano_teacher.lesson_generators import CodaLessonGenerator
    return LearningPlan(piece, exercise_strategy="coda-fukuda-midi",
                        lesson_generator=CodaLessonGenerator(teaching_passages=True),
                        **options)


def fukuda_course(piece: Piece, *, mistakes: frozenset[str] | None = None, **options):
    """The Fukuda component's own whole-score course (not selectable)."""
    from piano_teacher.learning import LearningPlan
    from piano_teacher.lesson_generators import FukudaMidiLessonGenerator
    return LearningPlan(piece, exercise_strategy="coda-fukuda-midi",
                        lesson_generator=FukudaMidiLessonGenerator(mistakes=mistakes),
                        **options)

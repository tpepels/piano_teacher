"""Compose source-preserving note selection, rhythm and tempo policies.

The public ExerciseVariant and stage-key schema remain unchanged. Explicit
ExerciseStage metadata carries timing/notation decisions into the application;
no transport or engraving code needs to inspect variant level strings.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from .exercise_generator import ExerciseVariant
from .notation.rhythm_safety import rhythm_protected_source_ids
from .exercise_strategies import ExerciseContext, ExerciseStrategy
from .exercise_contracts import (
    OriginalTiming, TempoMap, TempoStrategy, TimingStrategy,
)


@dataclass(frozen=True)
class ExerciseStage:
    variant: ExerciseVariant
    transformed_rhythm: bool = False
    tempo_policy: TempoStrategy | None = None

    @property
    def shaped_tempo(self) -> bool:
        return self.tempo_policy is not None

    def tempo_map(self, bpm: float) -> TempoMap | None:
        if self.tempo_policy is None:
            return None
        timing = OriginalTiming().transform(self.variant)
        return self.tempo_policy.generate(timing, bpm)


@dataclass(frozen=True)
class ExercisePipeline:
    exercise: ExerciseStrategy
    timing: TimingStrategy
    tempo: TempoStrategy

    def build(
        self, context: ExerciseContext,
        baseline: Callable[[], tuple[ExerciseVariant, ...]],
        *, source_musicxml: str = "",
    ) -> tuple[ExerciseStage, ...]:
        variants = self.exercise.generate(context, baseline)
        if context.warmup or context.kind != "learn" or not variants:
            return tuple(ExerciseStage(variant) for variant in variants)

        original = variants[-1]
        result = [ExerciseStage(variant) for variant in variants[:-1]]
        transformed = None
        if not getattr(self.timing, "is_identity", False) and context.hand != "both":
            mapping = self.timing.transform(original)
            if len(mapping.events) != len(original.notes):
                raise ValueError("Timing strategy must preserve note identities")
            changed = tuple(
                note.source_id for event, note in zip(mapping.events, original.notes)
                if abs(event.exercise_start - (note.start-original.phrase.start)) > 1e-7
                or abs(event.exercise_end - (note.end-original.phrase.start)) > 1e-7
            )
            # A merged tie attack cannot be retimed independently of its
            # written continuations. The same applies to authored tuplets.
            protected = rhythm_protected_source_ids(source_musicxml)
            if changed and not (set(changed) & protected):
                offset = original.phrase.start
                altered = tuple(replace(note, start=offset+event.exercise_start,
                                        end=offset+event.exercise_end)
                                for event, note in zip(mapping.events, original.notes))
                transformed = ExerciseVariant(
                    self.timing.name, replace(original.phrase, notes=altered),
                    original.source_indices)
                result.append(ExerciseStage(transformed, transformed_rhythm=True))

        if not getattr(self.tempo, "is_identity", False):
            result.append(ExerciseStage(
                ExerciseVariant(self.tempo.name, original.phrase,
                                original.source_indices), tempo_policy=self.tempo))
            if transformed is not None:
                result.append(ExerciseStage(
                    ExerciseVariant(
                        self.timing.name + "+" + self.tempo.name,
                        transformed.phrase, transformed.source_indices),
                    transformed_rhythm=True, tempo_policy=self.tempo))

        result.append(ExerciseStage(original))
        return tuple(result)

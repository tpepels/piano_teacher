"""One playable lesson stage: source notes plus timing and tempo metadata.

The public ExerciseVariant and stage-key schema remain unchanged. Explicit
ExerciseStage metadata carries timing/notation decisions into the application;
no transport or engraving code needs to inspect variant level strings.
"""
from __future__ import annotations

from dataclasses import dataclass

from .exercise_generator import ExerciseVariant
from .exercise_contracts import OriginalTiming, TempoMap, TempoStrategy


@dataclass(frozen=True)
class ExerciseStage:
    variant: ExerciseVariant
    transformed_rhythm: bool = False
    tempo_policy: TempoStrategy | None = None
    # Generator-owned, declarative teaching metadata. The application never
    # parses variant.level strings to decide who produced an exercise or
    # how to present it. Custom generators can publish their own categories.
    origin: str = ""
    technique: str = ""
    display_name: str = ""

    @property
    def shaped_tempo(self) -> bool:
        return self.tempo_policy is not None

    def tempo_map(self, bpm: float) -> TempoMap | None:
        if self.tempo_policy is None:
            return None
        timing = OriginalTiming().transform(self.variant)
        return self.tempo_policy.generate(timing, bpm)

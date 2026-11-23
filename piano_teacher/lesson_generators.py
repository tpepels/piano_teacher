"""Coda and Fukuda simplifications offered as Practice Flow's Free aid.

Practice Flow announces one simplified version of the selected window on
the second return to Free (docs/practice-flow.md). These contributors only
propose source-backed simplified stages for that exact window; they never
select passages or decide the lesson.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from .exercise_pipeline import ExerciseStage
from .exercise_generator import ExerciseVariant
from .music import Piece


@dataclass(frozen=True)
class CodaAid:
    """Coda category reductions of one authored MIDI window."""

    def passage_stages(self, piece: Piece, original: ExerciseVariant, *,
                       kind: str) -> tuple[ExerciseStage, ...]:
        from .application.coda_midi_curriculum import midi_coda_stages
        phrase = original.phrase
        if (kind == "learn" and (phrase.sounding_end > phrase.end+1e-7 or
                abs(phrase.end - piece.bar_boundaries[phrase.last_bar]) > 1e-7)):
            # A sounding MIDI release beyond the barline cannot be
            # transformed at authored meter boundaries.
            return (ExerciseStage(original, origin="original",
                                  technique="original",
                                  display_name="Original notes and rhythm"),)
        return midi_coda_stages(piece, (original,), kind=kind)


@dataclass(frozen=True)
class FukudaAid:
    """Fukuda note reductions, restricted to previously failed note IDs."""
    mistakes: frozenset[str] | None = None

    def passage_stages(self, piece: Piece, original: ExerciseVariant, *,
                       kind: str) -> tuple[ExerciseStage, ...]:
        from .fukuda_midi import fukuda_midi_variants, as_fukuda_stage
        variants = (fukuda_midi_variants(original, bpm=piece.bpm,
                    mistakes=self.mistakes) if kind == "learn" else (original,))
        return tuple(as_fukuda_stage(variant) for variant in variants)

    def with_feedback(self, evidence: Mapping[str, str], _definition) -> "FukudaAid":
        failed = frozenset(evidence)
        return replace(self, mistakes=failed) if failed != self.mistakes else self

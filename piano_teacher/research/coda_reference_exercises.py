"""Source-traceable exercises following the original Coda backend's categories.

This is an independent research adapter, not a copy of the author's code.
Reference: Tang (2025), §2.3, pp.11–16; annieetang/coda_backend
music/exercise.py at a4eb85dfc2bd418818ca9ff775c0a11ccccb3530.

The author's backend uses equal-duration runs, per-voice matrices and
factors 2/4 for written slowdown. Known unguarded bugs (out-of-bounds
subgroups, nested pitch list, silent rounding) are deliberately not
reproduced. Unsupported inputs fail closed and the differences are
documented; this is reference-guided, not blanket parity.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from ..exercise_contracts import OriginalTiming, TimingPlan
from ..exercise_generator import ExerciseVariant
from ..music import Phrase
from .coda_matrix import MatrixScore, MatrixVoice
from .coda_reference_matrix import CodaVoiceMatrix, score_voice_matrices


@dataclass(frozen=True)
class CodaLevelSelection:
    level: str
    variant: ExerciseVariant
    hand: str
    voice: str | None


@dataclass(frozen=True)
class CodaReferenceResult:
    family: str
    timing: TimingPlan
    changed_sources: tuple[str,...]
    groups: tuple[tuple[str,...],...]


def original_coda_levels(variant: ExerciseVariant, *,
                         boundaries: tuple[float,...],
                         source_musicxml: str = "") -> tuple[CodaLevelSelection,...]:
    """Actual Coda Score → Part → Voice isolation, NOT measure splitting."""
    matrix=MatrixScore.from_phrase(
        variant.phrase,boundaries=boundaries,source_musicxml=source_musicxml)
    result=[CodaLevelSelection("score",variant,"both",None)]
    for part in matrix.parts:
        ids=tuple(index for voice in part.voices
                  for attack in voice.attacks for index in attack.source_indices)
        if not ids:
            continue
        indices=tuple(i for i in range(len(variant.notes)) if i in set(ids))
        subset=_select(variant,indices,f"coda-part-{part.hand}")
        result.append(CodaLevelSelection("part",subset,part.hand,None))
        for voice in part.voices:
            source_indices={i for attack in voice.attacks for i in attack.source_indices}
            indices=tuple(i for i in range(len(variant.notes)) if i in source_indices)
            result.append(CodaLevelSelection(
                "voice",_select(variant,indices,"coda-voice-"+voice.name),
                part.hand,voice.name))
    return tuple(result)


def _select(original:ExerciseVariant,indices:tuple[int,...],name:str)->ExerciseVariant:
    p=original.phrase
    phrase=Phrase(p.number,p.first_bar,p.last_bar,p.start,p.end,
                  tuple(p.notes[i] for i in indices))
    return ExerciseVariant(name,phrase,tuple(original.source_indices[i] for i in indices))






def _source(score:MatrixScore, variant:ExerciseVariant, quantization:int):
    matrices=score_voice_matrices(score,quantization=quantization)
    paired=[]
    for part in score.parts:
        for voice in part.voices:
            matrix=next(m for m in matrices
                        if m.voice==voice.name and m.hand==part.hand)
            paired.append((voice,matrix))
    return paired









"""MIDI-first Coda exercise stages for the existing whole-piece LearningPlan.

Coda is chosen once as a *piece-level lesson-generation strategy*. The
existing curriculum selects its source passages and hands; this module
generates progressive per-passage exercises using the actual MIDI attacks.
All stages are ordinary ExerciseStage objects and share the standard score,
Listen, assessment, transport and persistence path. No temporary lesson.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..exercise_contracts import OriginalTiming, TempoMap, TempoSegment
from ..exercise_generator import ExerciseVariant
from ..exercise_pipeline import ExerciseStage
from ..music import Piece
from ..research.coda_midi_grid import midi_coda_quantization
from ..research.coda_reference_exercises import (
    CodaReferenceChordification, CodaReferenceDotted, original_coda_levels,
)


@dataclass(frozen=True)
class CodaHalfSpeed:
    """Play the written source at half the active rung's BPM."""
    name: str = "coda-half-speed"

    def generate(self, plan, bpm: float) -> TempoMap:
        if bpm <= 0:
            raise ValueError("Coda tempo must be positive")
        return TempoMap(self.name, (
            TempoSegment(0.0, plan.duration_beats, float(bpm) / 2.0),
        ))


def _retimed(original: ExerciseVariant, timing, name: str) -> ExerciseStage | None:
    """Use the exact source-indexed timing plan; reject null transforms."""
    if len(timing.events) != len(original.notes):
        raise ValueError("Coda lost source note ownership")
    phrase=original.phrase
    if abs(timing.duration_beats-(phrase.end-phrase.start))>1e-7:
        raise ValueError("Coda stage must retain this source passage length")
    altered=tuple(replace(note,
        start=phrase.start+event.exercise_start,
        end=phrase.start+event.exercise_end)
        for note,event in zip(original.notes,timing.events))
    if altered==original.notes:
        return None
    if {n.source_id for n in altered}!={n.source_id for n in original.notes}:
        raise ValueError("Coda changed original MIDI attack identities")
    if any(n.start < phrase.start-1e-7 or n.end>phrase.end+1e-7
           for n in altered):
        raise ValueError("Coda exercise crosses the selected passage")
    return ExerciseStage(
        ExerciseVariant(name,replace(phrase,notes=altered),
                        original.source_indices),
        transformed_rhythm=True)


def midi_coda_stages(
    piece: Piece, variants: tuple[ExerciseVariant, ...], *,
    kind: str,
) -> tuple[ExerciseStage, ...]:
    """Make one ordered Coda progression for one original-piece passage/hand.

    Unsupported groupings are omitted, while a complete original source
    stage always finishes the progression. MIDI scores never need
    authored MusicXML: the existing renderer generates written notation.
    """
    if piece.source_format!="midi" or piece.source_musicxml:
        raise ValueError("Coda MIDI lessons require an imported MIDI piece")
    if not variants:
        return ()
    if kind!="learn":
        return tuple(ExerciseStage(v) for v in variants)
    original=variants[-1]
    if original.level!="original":
        raise ValueError("Coda curriculum must finish with the source")
    stages=[ExerciseStage(v) for v in variants[:-1]]
    boundaries=tuple(
        beat for beat in piece.bar_boundaries
        if original.phrase.start-1e-7<=beat<=original.phrase.end+1e-7)
    if (boundaries and
            abs(boundaries[0]-original.phrase.start)<=1e-7 and
            abs(boundaries[-1]-original.phrase.end)<=1e-7):
        # Coda's actual hierarchy starts with isolated source voices,
        # then a part, then the complete score; all attacks remain tied
        # to the imported MIDI. The standard hand route already selects
        # parts, so an identical full-part stage would be redundant.
        try:
            hierarchy=original_coda_levels(
                original,boundaries=boundaries,source_musicxml="")
            used={tuple(n.source_id for n in original.notes)}
            for level in hierarchy:
                if level.level not in ("voice","part"):
                    continue
                key=tuple(n.source_id for n in level.variant.notes)
                if not key or key in used:
                    continue
                used.add(key)
                stages.append(ExerciseStage(level.variant))
        except ValueError:
            # Unsupported binary-matrix polyphony must not damage the
            # full source or suppress the safely playable original.
            pass
    stages.append(ExerciseStage(
        ExerciseVariant("coda-slowdown-x2",original.phrase,
                        original.source_indices),
        tempo_policy=CodaHalfSpeed()))
    if (not boundaries or
            abs(boundaries[0]-original.phrase.start)>1e-7 or
            abs(boundaries[-1]-original.phrase.end)>1e-7):
        # No representation-preserving rhythm operation exists without
        # exact original measure boundaries. Slowdown and original stay.
        stages.append(ExerciseStage(original))
        return tuple(stages)
    # A normal focus/bridge can have notes sustained beyond its ending;
    # never clip these notes or use an inexact source quantization.
    try:
        q=midi_coda_quantization(piece,original.phrase,compact=True)
        for name,transform in (
            ("coda-chord-blocks",
             lambda: CodaReferenceChordification(2*q).transform(
                 original,boundaries=boundaries,quantization=q,
                 source_musicxml="")),
            ("coda-dotted-long-short",
             lambda: CodaReferenceDotted(True).transform(
                 original,boundaries=boundaries,quantization=2*q,
                 source_musicxml="")),
            ("coda-dotted-short-long",
             lambda: CodaReferenceDotted(False).transform(
                 original,boundaries=boundaries,quantization=2*q,
                 source_musicxml="")),
        ):
            try:
                candidate=_retimed(original,transform().timing,name)
                if candidate is not None:
                    stages.append(candidate)
            except ValueError:
                # No corresponding exercise for this particular passage:
                # do not change the original source or claim a match.
                continue
    except ValueError:
        pass
    stages.append(ExerciseStage(original))
    return tuple(stages)

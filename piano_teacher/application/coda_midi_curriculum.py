"""Original-Coda excerpt catalog adapted to the MIDI-first teaching engine.

The pinned backend returns categorized exercise alternatives for a
caller-selected excerpt; it does not define curriculum order. These
normal ExerciseStages use an app-defined progression with the standard
notation, Listen and MIDI assessment owners. No shadow teaching session.
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
from ..research.coda_author_catalog import (
    AUTHOR_SLOWDOWN_FACTORS, catalog_requests,
)


@dataclass(frozen=True)
class CodaHalfSpeed:
    """MIDI playback adapter for the author's x2/x4 written slowdowns.

    Equivalent sounding duration at constant BPM; the original backend
    lengthens written notation instead. This difference is intentional.
    """
    factor: int = 2
    name: str = "coda-slowdown-tempo"

    def generate(self, plan, bpm: float) -> TempoMap:
        if bpm <= 0 or self.factor not in AUTHOR_SLOWDOWN_FACTORS:
            raise ValueError("Coda slowdown factor must be 2 or 4 and BPM positive")
        return TempoMap(self.name, (
            TempoSegment(0.0, plan.duration_beats, float(bpm)/self.factor),
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
    """Adapt all original excerpt-category requests into ordered app steps.

    The original Coda backend returns an UNORDERED catalog selected by a
    caller's measure range. Our teaching order is intentionally an app-only
    policy: voice → dotted/chord alternatives → slowdown → part → score.
    All requests for the full imported MIDI excerpt are considered, and
    unrepresentable/no-op variants are skipped without claiming parity.
    """
    if piece.source_format != "midi" or piece.source_musicxml:
        raise ValueError("Coda exercises need imported MIDI notes")
    if not variants:
        return ()
    original=variants[-1]
    if original.level!="original":
        raise ValueError("Coda lesson must end with original MIDI notes")
    if kind!="learn":
        return (ExerciseStage(original),)

    # The original's Score Level is the unchanged whole excerpt. Mixed
    # hands must not be retimed as a made-up cross-voice Coda operation.
    hands={n.hand for n in original.notes}
    if len(hands)>1:
        return (ExerciseStage(original),)

    phrase=original.phrase
    boundaries=tuple(t for t in piece.bar_boundaries
                     if phrase.start-1e-7<=t<=phrase.end+1e-7)
    exact_grid=(len(boundaries)>1 and
                abs(boundaries[0]-phrase.start)<=1e-7 and
                abs(boundaries[-1]-phrase.end)<=1e-7)
    # The Score/Part/Voice categories are source inventory. An author
    # voice is a subset of one hand. The final full part is mandatory.
    voices=(original,)
    if exact_grid:
        try:
            hierarchy=original_coda_levels(
                original,boundaries=boundaries,source_musicxml="")
            candidates=tuple(item.variant for item in hierarchy
                             if item.level=="voice")
            if candidates:
                unique={}
                for candidate in candidates:
                    ids=tuple(n.source_id for n in candidate.notes)
                    unique.setdefault(ids,candidate)
                voices=tuple(unique.values())
        except ValueError:
            pass

    stages=[]
    used_levels=set()
    def append(stage: ExerciseStage):
        if stage.variant.level in used_levels:
            raise ValueError("Duplicate Coda exercise level")
        used_levels.add(stage.variant.level)
        stages.append(stage)

    quantization=None
    if exact_grid:
        try:
            quantization=midi_coda_quantization(
                piece,phrase,compact=True)
        except ValueError:
            pass
    first_meter=next(
        ((n,d) for t,n,d in piece.time_signatures
         if t<=phrase.start+1e-7),(4,4))
    numerator,denominator=first_meter

    # Source authors generated per VOICE: dotted x2, ALL automatic
    # chordification widths, and slowdown x2 and x4. A MIDI source has no
    # authored MusicXML to preserve, so timing safety guards remain.
    for voice_index,voice in enumerate(voices):
        suffix=(f"-voice-{voice_index+1}" if len(voices)>1 else "")
        if voice.notes!=original.notes:
            append(ExerciseStage(ExerciseVariant(
                "coda-voice-original"+suffix,voice.phrase,
                voice.source_indices)))
        if quantization is not None:
            requests=catalog_requests(quantization,numerator,denominator)
            for req in requests:
                try:
                    if req.category=="Voice Level: Dotted":
                        transformed=CodaReferenceDotted(
                            req.parameter==(1.5,0.5)).transform(
                            voice,boundaries=boundaries,
                            quantization=quantization*2,source_musicxml="")
                        name="coda-"+req.variant+suffix
                    elif req.category=="Voice Level: Chordified":
                        if not isinstance(req.parameter,int) or req.parameter<=0:
                            continue
                        transformed=CodaReferenceChordification(
                            req.parameter).transform(
                            voice,boundaries=boundaries,
                            quantization=quantization,source_musicxml="")
                        name="coda-"+req.variant+suffix
                    else:
                        continue
                    new=_retimed(voice,transformed.timing,name)
                    if new is not None:
                        append(new)
                except ValueError:
                    # Original may yield None, or our safety guard may
                    # reject its output. Never silently invent note timing.
                    continue
        for factor in AUTHOR_SLOWDOWN_FACTORS:
            append(ExerciseStage(
                ExerciseVariant(
                    f"coda-slowdown-x{factor}"+suffix,voice.phrase,
                    voice.source_indices),
                tempo_policy=CodaHalfSpeed(factor=factor)))
    append(ExerciseStage(original))
    return tuple(stages)

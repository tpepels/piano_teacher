"""Select any bounded bar-aligned excerpt from an imported MIDI piece.

An excerpt owns local beat coordinates for notation, Listen and grading,
while the immutable full source retains each original physical attack/release.
No note may be clipped silently at a passage boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isclose
from hashlib import sha256

from ..exercise_generator import ExerciseVariant
from ..music import KeySignature, ClefChange, Phrase, Piece


@dataclass(frozen=True)
class MidiPassage:
    source_piece: Piece
    piece: Piece
    variant: ExerciseVariant
    first_bar: int
    last_bar: int
    source_start: float
    source_end: float
    source_indices: tuple[int, ...]

    @property
    def original_source_ids(self) -> frozenset[str]:
        return frozenset(note.source_id for note in self.variant.notes)

    def original_coordinates(self) -> dict[str, tuple[float, float]]:
        return {
            note.source_id: (note.start, note.end)
            for index in self.source_indices
            for note in (self.source_piece.notes[index],)
        }


def _active_initial(values, start: float, beat_of) -> tuple:
    # Include the context active at the requested source bar, rebased
    # to zero, plus every actual change inside this passage.
    previous = [item for item in values if beat_of(item) <= start + 1e-8]
    return (replace(previous[-1],beat=0.0),) if previous else ()


def select_midi_passage(
    piece: Piece, first_bar: int, last_bar: int, *,
    max_measures: int = 8,
) -> MidiPassage:
    if piece.source_format != "midi" or piece.source_musicxml or piece.midi_ticks_per_beat <= 0:
        raise ValueError("Passage selection requires a genuine imported MIDI file")
    boundaries = piece.bar_boundaries
    if (not isinstance(first_bar,int) or not isinstance(last_bar,int) or
            first_bar<1 or last_bar<first_bar or
            last_bar>=len(boundaries)):
        raise ValueError("Invalid MIDI passage bar numbers")
    if max_measures <= 0 or last_bar-first_bar+1>max_measures:
        raise ValueError("Selected MIDI passage exceeds permitted measure count")
    start,end=boundaries[first_bar-1],boundaries[last_bar]
    if not end>start:
        raise ValueError("Empty MIDI measure selection")
    # A note whose attack occurs before this passage must not appear as
    # an invented attack at beat zero. A note whose release crosses the
    # ending must not be silently shortened.
    for n in piece.notes:
        if n.start<start-1e-7 and n.end>start+1e-7:
            raise ValueError("MIDI passage begins during a sustained note")
        if n.start<end-1e-7 and n.end>end+1e-7:
            raise ValueError("MIDI passage ends during a sustained note")
    indices=tuple(i for i,n in enumerate(piece.notes)
                  if start-1e-7<=n.start<end-1e-7)
    if not indices:
        raise ValueError("Selected MIDI passage contains no note attacks")
    originals=tuple(piece.notes[i] for i in indices)
    if len({n.source_id for n in originals})!=len(originals):
        raise ValueError("Selected source attack identities are not unique")
    notes=tuple(replace(n,start=round(n.start-start,8),
                        end=round(n.end-start,8))
                for n in originals)
    local_boundaries=tuple(round(beat-start,8)
                           for beat in boundaries[first_bar-1:last_bar+1])
    signatures=[(t,n,d) for t,n,d in piece.time_signatures
                if t<=start+1e-7]
    active=signatures[-1] if signatures else (0.0,4,4)
    meters=[(0.0,active[1],active[2])]
    meters.extend((round(t-start,8),n,d)
                  for t,n,d in piece.time_signatures
                  if start+1e-7<t<end-1e-7)
    keys=_active_initial(piece.key_signatures,start,lambda x:x.beat)
    keys+=tuple(replace(k,beat=round(k.beat-start,8))
                for k in piece.key_signatures if start+1e-7<k.beat<end-1e-7)
    clefs=_active_initial(piece.clef_changes,start,lambda x:x.beat)
    clefs+=tuple(replace(c,beat=round(c.beat-start,8))
                  for c in piece.clef_changes if start+1e-7<c.beat<end-1e-7)
    phrase=Phrase(first_bar,1,len(local_boundaries)-1,0.0,
                  local_boundaries[-1],notes)
    excerpt=replace(
        piece,notes=notes,phrases=(phrase,),
        bar_boundaries=local_boundaries,time_signatures=tuple(meters),
        key_signatures=keys,clef_changes=clefs,
        barlines=(),fingering_plan=None)
    variant=ExerciseVariant(
        f"midi-bars-{first_bar}-{last_bar}",phrase,indices)
    return MidiPassage(piece,excerpt,variant,first_bar,last_bar,start,end,indices)


def project_midi_passage(
    piece: Piece, first_bar: int, last_bar: int, *,
    family: str, slowdown_factor: int = 2,
    long_first: bool = True, chord_beats: float = 2,
    bpm: float | None = None, revision: int = 1,
):
    """One selected MIDI passage -> one Coda-derived research stage.

    The returned MidiPassage separately owns immutable absolute source
    coordinates. The stage consumes passage-relative beats consistently.
    """
    from .coda_midi_grid import midi_coda_quantization
    from .coda_reference_exercises import (
        CodaReferenceSlowdown, CodaReferenceDotted, CodaReferenceChordification,
    )
    from .coda_score_projection import project_coda_score

    passage=select_midi_passage(piece,first_bar,last_bar)
    original=passage.variant
    if family=="tempo-shaping":
        plan=CodaReferenceSlowdown(slowdown_factor).transform(original).timing
    elif family=="dotted-rhythms":
        q=midi_coda_quantization(passage.piece,original.phrase,
                                 dotted=True,compact=True)
        plan=CodaReferenceDotted(long_first).transform(
            original,boundaries=passage.piece.bar_boundaries,
            quantization=q,source_musicxml="").timing
    elif family=="chordification":
        q=midi_coda_quantization(passage.piece,original.phrase,compact=True)
        units=chord_beats*q
        if units<=0 or not isclose(units,round(units),abs_tol=1e-7):
            raise ValueError("Chord grouping requires a positive integral MIDI grid width")
        plan=CodaReferenceChordification(round(units)).transform(
            original,boundaries=passage.piece.bar_boundaries,
            quantization=q,source_musicxml="").timing
    else:
        raise ValueError("Unsupported MIDI Coda practice family")
    stage=project_coda_score(
        passage.piece,plan,reference_family=family,
        bpm=bpm if bpm is not None else piece.bpm,revision=revision)
    return passage,stage

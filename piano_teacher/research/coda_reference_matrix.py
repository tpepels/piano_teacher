"""Reference-guided Coda voice matrices (Annie Tang, 2025, section 2.2).

Independent implementation informed by the published thesis and author's
public backend at pinned revision a4eb85dfc2bd418818ca9ff775c0a11ccccb3530.
The lossless MatrixScore continues to own the original source; this adapter
constructs the author's three 128-pitch x quantized-time matrices for each
voice without silently rounding away source timing or merging source IDs.
No implication of complete reference parity or pedagogical effectiveness.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite

import numpy as np

from .coda_matrix import MatrixScore, MatrixVoice


def reference_quantization(shortest_quarter_length: float, time_numerator: int) -> int:
    """Coda's backend: ceil(1 / shortest note length) * meter numerator.

    The published formula is nonstandard. Retain it explicitly for
    reproducibility, rather than silently replacing it with a music21 grid.
    """
    if (not isfinite(shortest_quarter_length) or shortest_quarter_length <= 0
            or time_numerator <= 0):
        raise ValueError("Coda quantization requires a positive rhythm and meter")
    return ceil(1 / shortest_quarter_length) * time_numerator


def _tick(relative_beat: float, quantization: int) -> int:
    ticks = relative_beat * quantization
    nearest = round(ticks)
    # MatrixScore stores source onsets to eight decimal places.
    # A genuine 2/7-quarter note is therefore 0.28571429 and yields
    # a ~3e-7 tick discrepancy at quantization=70. Compare in beat
    # units at the source's 1e-8 precision; never round a genuinely
    # off-grid event to an unrelated tick.
    if not isfinite(ticks) or abs(ticks-nearest)/quantization > 1e-8 or nearest < 0:
        raise ValueError("Source onset/release is not exactly representable on Coda grid")
    return nearest


@dataclass(frozen=True)
class CodaVoiceMatrix:
    """Original piano roll, onset map and duration matrix for ONE voice."""

    voice: str
    hand: str
    quantization: int
    phrase_start: float
    piano_roll: np.ndarray
    onset_map: np.ndarray
    durations_matrix: np.ndarray
    owners: tuple[tuple[int, int, int, str], ...]  # pitch, tick, source index, id

    @classmethod
    def from_voice(cls, score: MatrixScore, voice: MatrixVoice, *,
                   hand: str, quantization: int) -> "CodaVoiceMatrix":
        if not isinstance(quantization, int) or quantization <= 0:
            raise ValueError("Coda quantization must be a positive integer")
        events = []
        for attack in voice.attacks:
            for pitch, end, index, identifier in zip(
                    attack.pitches, attack.ends,
                    attack.source_indices, attack.source_ids):
                start_tick = _tick(attack.onset - score.phrase.start, quantization)
                end_tick = _tick(end - score.phrase.start, quantization)
                if not 0 <= pitch <= 127 or end_tick <= start_tick:
                    raise ValueError("Invalid quantized source pitch/duration")
                events.append((int(pitch),start_tick,end_tick,int(index),identifier))
        length = max((item[2] for item in events),default=0)
        if length * 128 > 2_000_000:
            raise ValueError("Coda matrix would exceed bounded reference size")
        roll = np.zeros((128,length),dtype=np.uint8)
        onsets = np.zeros((128,length),dtype=np.uint8)
        durations = np.zeros((128,length),dtype=np.int32)
        owners = []
        for pitch,start,end,index,identifier in events:
            if np.any(roll[pitch,start:end]):
                # Same-pitch collisions are unrepresentable in a 128-row
                # binary matrix. Report this, never silently drop a voice.
                raise ValueError("Coda piano roll cannot represent overlapping identical pitch")
            roll[pitch,start:end] = 1
            onsets[pitch,start] = 1
            durations[pitch,start] = end-start
            owners.append((pitch,start,index,identifier))
        return cls(voice.name,hand,quantization,score.phrase.start,
                   roll,onsets,durations,tuple(owners))

    @property
    def steps(self) -> int:
        return self.piano_roll.shape[1]

    def verify(self) -> None:
        if any(m.shape != self.piano_roll.shape for m in (
                self.onset_map,self.durations_matrix)):
            raise ValueError("Coda matrix shapes differ")
        if self.piano_roll.shape[0] != 128:
            raise ValueError("Coda matrix must have 128 MIDI pitch rows")
        rebuilt = np.zeros_like(self.piano_roll)
        if not np.array_equal(self.onset_map,(self.durations_matrix>0).astype(np.uint8)):
            raise ValueError("Coda onsets and positive durations differ")
        for pitch,start,index,identifier in self.owners:
            duration = int(self.durations_matrix[pitch,start])
            if duration <= 0 or start+duration > self.steps:
                raise ValueError("Coda source owner has invalid duration")
            if np.any(rebuilt[pitch,start:start+duration]):
                raise ValueError("Coda duration reconstruction overlaps same pitch")
            rebuilt[pitch,start:start+duration] = 1
        if not np.array_equal(rebuilt,self.piano_roll):
            raise ValueError("Coda piano roll and source durations differ")
        if int(np.count_nonzero(self.onset_map)) != len(self.owners):
            raise ValueError("Coda source attack ownership was lost")

    def flatten(self) -> tuple[tuple[int, ...], dict[int, tuple[int, ...]]]:
        """Linear rhythms and simultaneous pitch sets, matching the MMR API.

        Author's algorithm assumes simultaneous pitches have equal written
        durations. Reject conflicting source durations rather than
        arbitrarily selecting the smallest MIDI pitch's duration.
        """
        flat = []
        pitches = {}
        for tick in range(self.steps):
            sounding = tuple(int(p) for p in np.flatnonzero(self.onset_map[:,tick]))
            pitches_at = [int(self.durations_matrix[p,tick]) for p in sounding]
            if len(set(pitches_at)) > 1:
                raise ValueError("Coda linear voice has unequal simultaneous durations")
            flat.append(pitches_at[0] if pitches_at else 0)
            if sounding:
                pitches[tick] = sounding
        return tuple(flat),pitches

    def equal_duration_ranges(self) -> tuple[tuple[int,int,int],...]:
        """Consecutive written attacks of identical duration (start,end,count)."""
        flat,_ = self.flatten()
        ranges = []
        start = -1
        value = -1
        count = 0
        for tick,duration in enumerate(flat):
            if not duration:
                continue
            if duration != value:
                if count>1:
                    ranges.append((start,tick,count))
                value,start,count = duration,tick,1
            else:
                count += 1
        if count>1:
            ranges.append((start,len(flat),count))
        return tuple(ranges)


def score_voice_matrices(score: MatrixScore, *,
                         quantization: int) -> tuple[CodaVoiceMatrix,...]:
    """Build all note-bearing source voices, keeping rests in MatrixScore."""
    result=[]
    for part in score.parts:
        for voice in part.voices:
            item=CodaVoiceMatrix.from_voice(
                score,voice,hand=part.hand,quantization=quantization)
            item.verify()
            result.append(item)
    return tuple(result)

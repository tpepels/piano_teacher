"""Explainable source-score difficulty features and swappable difficulty policy.

This is a deterministic feature baseline, not the trained RubricNet network.
It operates on one selected hand and the original source onsets without
modifying score events or granting any pedagogical outcome.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Protocol

from .music import Note


@dataclass(frozen=True)
class DifficultyFeatures:
    note_count: int
    attack_count: int
    beats: float
    peak_chord_size: int
    max_simultaneous_span: int
    max_melodic_leap: int
    rapid_intervals: int
    offbeat_attacks: int
    sustained_overlaps: int
    min_attack_gap: float

    @property
    def attacks_per_beat(self) -> float:
        return self.attack_count / max(self.beats, 1e-6)

    def as_dict(self) -> dict:
        return {
            "note_count": self.note_count, "attack_count": self.attack_count,
            "beats": self.beats, "peak_chord_size": self.peak_chord_size,
            "max_simultaneous_span": self.max_simultaneous_span,
            "max_melodic_leap": self.max_melodic_leap,
            "rapid_intervals": self.rapid_intervals,
            "offbeat_attacks": self.offbeat_attacks,
            "sustained_overlaps": self.sustained_overlaps,
            "min_attack_gap": self.min_attack_gap,
            "attacks_per_beat": self.attacks_per_beat,
        }


@dataclass(frozen=True)
class DifficultyEstimate:
    level: str
    focus: str
    reasons: tuple[str, ...]
    features: DifficultyFeatures


class DifficultyEstimator(Protocol):
    name: str

    def estimate(self, notes: tuple[Note, ...], duration_beats: float
                 ) -> DifficultyEstimate: ...


@dataclass(frozen=True)
class HeuristicDifficulty:
    name: str = "interpretable-v1"

    def estimate(self, notes: tuple[Note, ...], duration_beats: float) -> DifficultyEstimate:
        by_attack = defaultdict(list)
        by_voice = defaultdict(list)
        for note in notes:
            by_attack[(note.hand, round(note.start, 6))].append(note)
            by_voice[(note.hand, note.track, note.voice)].append(note)
        attacks = sorted({round(note.start, 6) for note in notes})
        gaps = [b - a for a, b in zip(attacks, attacks[1:])]
        peak = max((len(group) for group in by_attack.values()), default=0)
        span = max((max(n.pitch for n in group) - min(n.pitch for n in group)
                    for group in by_attack.values()), default=0)
        leap = 0
        overlaps = 0
        for voice in by_voice.values():
            voice.sort(key=lambda note: (note.start, note.pitch))
            for a, b in zip(voice, voice[1:]):
                if b.start > a.start + 1e-7:
                    leap = max(leap, abs(a.pitch - b.pitch))
                if b.start < a.end - 1e-7:
                    overlaps += 1
        features = DifficultyFeatures(
            len(notes), len(attacks), duration_beats, peak, span, leap,
            sum(0 < gap < .5 - 1e-7 for gap in gaps),
            sum(abs(t * 2 - round(t * 2)) > .04 for t in attacks),
            overlaps, min(gaps, default=duration_beats),
        )
        reasons = []
        if peak >= 3:
            reasons.append("three-or-more-note chords")
        if span >= 12 and peak >= 2:
            reasons.append("wide simultaneous spans")
        if leap >= 12:
            reasons.append("octave-or-greater voice leaps")
        if features.rapid_intervals >= 3:
            reasons.append("rapid successive attacks")
        if features.sustained_overlaps >= 2:
            reasons.append("overlapping voice attacks")
        if features.offbeat_attacks >= 4:
            reasons.append("irregular subdivisions")
        if reasons:
            focus = ("chords" if peak >= 3 or span >= 12 else
                     "leaps" if leap >= 12 else "rhythm")
            return DifficultyEstimate("challenging", focus, tuple(reasons), features)
        return DifficultyEstimate("baseline", "none", (), features)

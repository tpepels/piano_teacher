"""Experimental polyphonic chordification over immutable Coda-style voices.

This is an independently testable extension, *not* a claim of exact Coda
reference implementation. It never crosses a source measure or combines
different voices, hands or original repeated pitches. Untouched source notes
retain their exact IDs and timing; exercise beat changes are explicitly
reversible in TimingPlan. Original-source mastery remains separate.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..exercise_contracts import OriginalTiming, TimingPlan
from ..exercise_generator import ExerciseVariant
from .coda_matrix import MatrixAttack, MatrixScore


@dataclass(frozen=True)
class ChordificationDecision:
    hand: str
    voice: str
    measure: int
    first_source_ids: tuple[str, ...]
    second_source_ids: tuple[str, ...]
    moved_to_beat: float


@dataclass(frozen=True)
class ChordificationResult:
    timing: TimingPlan
    decisions: tuple[ChordificationDecision, ...]


@dataclass(frozen=True)
class PolyphonicChordifier:
    """Combine eligible consecutive *chords* separately in each piano voice."""

    name: str = "coda-polyphonic-chordification-prototype"

    def transform(self, variant: ExerciseVariant, *,
                  boundaries: tuple[float, ...] = (),
                  protected_ids: frozenset[str] = frozenset()
                  ) -> ChordificationResult:
        source = MatrixScore.from_phrase(variant.phrase, boundaries=boundaries)
        original = OriginalTiming().transform(variant)
        events = list(original.events)
        actions = []
        origin = variant.phrase.start
        for part in source.parts:
            for voice in part.voices:
                attacks = voice.attacks
                for i in range(0, len(attacks) - 1, 2):
                    first, second = attacks[i], attacks[i + 1]
                    if not self._eligible(first, second, source,
                                          protected_ids):
                        continue
                    new_beat = first.onset - origin
                    for index in second.source_indices:
                        source_event = events[index]
                        offset = new_beat
                        end = offset + (source_event.source_end-source_event.source_start)
                        events[index] = replace(
                            source_event, exercise_start=offset, exercise_end=end)
                    actions.append(ChordificationDecision(
                        part.hand, voice.name, first.measure, first.source_ids,
                        second.source_ids, new_beat))
        plan = TimingPlan(self.name, variant, tuple(events),
                          original.duration_beats)
        return ChordificationResult(plan, tuple(actions))

    @staticmethod
    def _eligible(a: MatrixAttack, b: MatrixAttack, matrix: MatrixScore,
                  protected: frozenset[str]) -> bool:
        if (a.measure != b.measure
                or any(identifier in protected for identifier
                       in (*a.source_ids, *b.source_ids))
                or set(a.pitches) & set(b.pitches)):
            return False
        # Every note must be able to participate as a single duration-chord.
        # Overlapping or independently sustained source voices cannot be
        # collapsed into a fake same-stem chord.
        durations = tuple(end-a.onset for end in a.ends) + tuple(
            end-b.onset for end in b.ends)
        if not durations or max(durations)-min(durations) > 1e-6:
            return False
        duration = durations[0]
        if abs(b.onset-a.onset-duration) > 1e-6:
            return False
        bar = a.measure-matrix.phrase.first_bar
        if a.onset < matrix.boundaries[bar]-1e-7:
            return False
        if b.onset+duration > matrix.boundaries[bar+1]+1e-7:
            return False
        return True

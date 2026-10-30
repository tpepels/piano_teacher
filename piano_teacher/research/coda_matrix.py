"""Immutable Score–Part–Voice attack matrix for research exercise generation.

A source-backed symbolic adapter, *not* a reproduction of Coda's complete
MMR. Notes remain attached to their original attack IDs, track/channel,
voice and measure; source events are never rewritten in this representation.
Authored rests/ornaments/notations require independent MusicXML semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right
from math import isfinite

from ..music import Note, Phrase, source_note_id


@dataclass(frozen=True)
class MatrixAttack:
    onset: float
    source_indices: tuple[int, ...]
    source_ids: tuple[str, ...]
    pitches: tuple[int, ...]
    ends: tuple[float, ...]
    measure: int

    def __post_init__(self):
        if (not self.source_indices or len(self.source_indices) != len(self.source_ids)
                or len(self.source_ids) != len(self.pitches)
                or len(self.pitches) != len(self.ends)
                or not isfinite(self.onset)
                or any(not isfinite(end) or end <= self.onset for end in self.ends)
                or len(set(self.source_indices)) != len(self.source_indices)
                or len(set(self.source_ids)) != len(self.source_ids)):
            raise ValueError("Invalid source attack group")


@dataclass(frozen=True)
class MatrixVoice:
    track: int
    channel: int
    name: str
    attacks: tuple[MatrixAttack, ...]

    def __post_init__(self):
        if not all(a.onset <= b.onset for a, b in zip(self.attacks, self.attacks[1:])):
            raise ValueError("Voice attacks not chronologically ordered")


@dataclass(frozen=True)
class MatrixPart:
    hand: str
    voices: tuple[MatrixVoice, ...]

    def __post_init__(self):
        if self.hand not in ("left", "right"):
            raise ValueError("Unknown staff part")


@dataclass(frozen=True)
class MatrixScore:
    """Lossless partition of the selected phrase's source note events.

    The part boundary follows the imported exercise's hand ownership, while
    each written source voice/track/channel keeps its own simultaneous attacks.
    """
    phrase: Phrase
    boundaries: tuple[float, ...]
    parts: tuple[MatrixPart, ...]
    index_to_source: tuple[tuple[int, str], ...]

    @classmethod
    def from_phrase(cls, phrase: Phrase, *, boundaries: tuple[float, ...] = ()):
        if boundaries:
            grid = tuple(float(x) for x in boundaries
                         if phrase.start - 1e-7 <= x <= phrase.end + 1e-7)
            if not grid or abs(grid[0] - phrase.start) > 1e-7:
                grid = (phrase.start, *grid)
            if abs(grid[-1] - phrase.end) > 1e-7:
                grid += (phrase.end,)
        else:
            grid = (phrase.start, phrase.end)
        if (len(grid) < 2 or any(not isfinite(x) for x in grid)
                or any(b <= a for a, b in zip(grid, grid[1:]))):
            raise ValueError("Invalid measure grid")
        voices: dict[tuple[str, int, int, str], dict[float, list[tuple[int, Note]]]] = {}
        seen_ids: set[str] = set()
        identities = []
        for i, note in enumerate(phrase.notes):
            identifier = source_note_id(note, i)
            if (identifier in seen_ids or note.hand not in ("left", "right")
                    or not isfinite(note.start) or not isfinite(note.end)
                    or not phrase.start - 1e-7 <= note.start < phrase.end - 1e-7
                    or note.end <= note.start):
                raise ValueError("Invalid or duplicate score note identity")
            seen_ids.add(identifier)
            identities.append((i, identifier))
            key = (note.hand, note.track, note.channel, note.voice)
            onset = round(note.start, 8)
            voices.setdefault(key, {}).setdefault(onset, []).append((i, note))
        parts = []
        for hand in ("right", "left"):
            part_voices = []
            for (owner, track, channel, name), by_onset in sorted(voices.items()):
                if owner != hand:
                    continue
                attacks = []
                for onset, members in sorted(by_onset.items()):
                    member_indices = tuple(i for i, _ in members)
                    measure_offset = bisect_right(grid, onset) - 1
                    if not 0 <= measure_offset < len(grid) - 1:
                        raise ValueError("Attack outside the measure grid")
                    attacks.append(MatrixAttack(
                        onset, member_indices,
                        tuple(identities[i][1] for i in member_indices),
                        tuple(n.pitch for _, n in members),
                        tuple(n.end for _, n in members),
                        phrase.first_bar + measure_offset))
                part_voices.append(MatrixVoice(track, channel, name, tuple(attacks)))
            parts.append(MatrixPart(hand, tuple(part_voices)))
        result = cls(phrase, grid, tuple(parts), tuple(identities))
        result.verify_lossless()
        return result

    def verify_lossless(self) -> None:
        expected = dict(self.index_to_source)
        observed = []
        for part in self.parts:
            for voice in part.voices:
                for attack in voice.attacks:
                    for index, identifier, pitch, end in zip(
                            attack.source_indices, attack.source_ids,
                            attack.pitches, attack.ends):
                        if index not in expected or expected[index] != identifier:
                            raise ValueError("Score matrix changed source identity")
                        note = self.phrase.notes[index]
                        if (note.hand != part.hand or note.track != voice.track
                                or note.channel != voice.channel
                                or note.voice != voice.name
                                or abs(note.start - attack.onset) > 1e-7
                                or note.pitch != pitch or note.end != end):
                            raise ValueError("Score matrix changed a source event")
                        observed.append(index)
        if sorted(observed) != sorted(expected):
            raise ValueError("Score matrix lost or duplicated source events")

    @property
    def note_count(self) -> int:
        return len(self.index_to_source)

    @property
    def attack_count(self) -> int:
        return sum(len(voice.attacks) for part in self.parts for voice in part.voices)

    def source_indices(self) -> tuple[int, ...]:
        return tuple(index for index, _ in self.index_to_source)

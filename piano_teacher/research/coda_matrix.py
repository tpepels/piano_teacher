"""Immutable Score–Part–Voice attack matrix for research exercise generation.

A source-backed symbolic adapter, *not* a reproduction of Coda's complete
MMR. Notes remain attached to their original attack IDs, track/channel,
voice and measure; source events are never rewritten in this representation.
Authored rests are associated with source voices where possible, and
rest-only voices retain original source ownership without a guessed hand.
Other ornaments/notations still require independent MusicXML semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right
from math import isfinite

from ..music import Note, Phrase, source_note_id
from .coda_written_rests import MatrixWrittenRest, extract_written_rests


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
    written_rests: tuple[MatrixWrittenRest, ...] = ()

    def __post_init__(self):
        if not all(a.onset <= b.onset for a, b in zip(self.attacks, self.attacks[1:])):
            raise ValueError("Voice attacks not chronologically ordered")
        if any(rest.voice_id != self.name for rest in self.written_rests):
            raise ValueError("Written rest belongs to another source voice")


@dataclass(frozen=True)
class MatrixRestOnlyVoice:
    """Authored rests without a selected pitched voice; hand is intentionally unknown."""

    name: str
    written_rests: tuple[MatrixWrittenRest, ...]


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
    written_rests: tuple[MatrixWrittenRest, ...] = ()

    @classmethod
    def from_phrase(cls, phrase: Phrase, *, boundaries: tuple[float, ...] = (),
                    source_musicxml: str = ""):
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
        written_rests = extract_written_rests(
            source_musicxml, first_bar=phrase.first_bar, last_bar=phrase.last_bar,
            boundaries=grid) if source_musicxml else ()
        rests_by_voice: dict[str, list[MatrixWrittenRest]] = {}
        for rest in written_rests:
            rests_by_voice.setdefault(rest.voice_id, []).append(rest)
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
                part_voices.append(MatrixVoice(
                    track, channel, name, tuple(attacks),
                    tuple(rests_by_voice.get(name, ()))))
            parts.append(MatrixPart(hand, tuple(part_voices)))
        result = cls(phrase, grid, tuple(parts), tuple(identities), written_rests)
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
        rest_ids = tuple(rest.source_id for rest in self.written_rests)
        if len(rest_ids) != len(set(rest_ids)):
            raise ValueError("Score matrix duplicated written-rest identities")
        voice_rests = tuple(
            rest.source_id for part in self.parts for voice in part.voices
            for rest in voice.written_rests)
        rest_only = tuple(rest.source_id for voice in self.rest_only_voices
                          for rest in voice.written_rests)
        if sorted((*voice_rests, *rest_only)) != sorted(rest_ids):
            raise ValueError("Score matrix lost or duplicated written rests")

    @property
    def rest_only_voices(self) -> tuple[MatrixRestOnlyVoice, ...]:
        """Source voices absent from the selected pitch events, without guessed hands."""
        sounding = {voice.name for part in self.parts for voice in part.voices}
        missing: dict[str, list[MatrixWrittenRest]] = {}
        for rest in self.written_rests:
            if rest.voice_id not in sounding:
                missing.setdefault(rest.voice_id, []).append(rest)
        return tuple(MatrixRestOnlyVoice(name, tuple(missing[name]))
                     for name in sorted(missing))

    @property
    def note_count(self) -> int:
        return len(self.index_to_source)

    @property
    def written_rest_count(self) -> int:
        return len(self.written_rests)

    @property
    def attack_count(self) -> int:
        return sum(len(voice.attacks) for part in self.parts for voice in part.voices)

    def source_indices(self) -> tuple[int, ...]:
        return tuple(index for index, _ in self.index_to_source)

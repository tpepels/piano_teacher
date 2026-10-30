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
from .coda_source_metadata import MatrixSourceElement, source_elements
from .coda_notation_hierarchy import (
    MatrixMeasureContext, MatrixNotationPart, measure_contexts, notation_parts,
)


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
    notation_elements: tuple[MatrixSourceElement, ...] = ()
    source_contexts: tuple[MatrixMeasureContext, ...] = ()
    original_musicxml: str = ""

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
        notations = source_elements(
            source_musicxml, first_bar=phrase.first_bar, last_bar=phrase.last_bar,
            boundaries=grid) if source_musicxml else ()
        contexts = measure_contexts(
            source_musicxml, first_bar=phrase.first_bar, last_bar=phrase.last_bar,
            notation_elements=notations) if source_musicxml else ()
        result = cls(phrase, grid, tuple(parts), tuple(identities),
                     written_rests, notations, contexts, source_musicxml)
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
        ids = [item.source_id for item in self.notation_elements]
        if len(ids) != len(set(ids)):
            raise ValueError("Score matrix has duplicate source XML elements")
        authored = {item.source_id for item in self.notation_elements if item.is_rest}
        if self.notation_elements and authored != set(rest_ids):
            raise ValueError("Score matrix lost authored rest metadata")
        if self.original_musicxml:
            # Repartitioning the observed inventory alone is insufficient:
            # deleting an unvoiced dynamic/barline/note can otherwise leave
            # the reduced part graph internally consistent. Compare against
            # the immutable ORIGINAL source, element by element and in order.
            expected_source = source_elements(
                self.original_musicxml, first_bar=self.phrase.first_bar,
                last_bar=self.phrase.last_bar, boundaries=self.boundaries)
            if self.notation_elements != expected_source:
                raise ValueError("Score matrix changed source notation inventory")
            rebuilt = measure_contexts(
                self.original_musicxml, first_bar=self.phrase.first_bar,
                last_bar=self.phrase.last_bar,
                notation_elements=self.notation_elements)
            if rebuilt != self.source_contexts:
                raise ValueError("Score matrix lost source notation context")
            parts = self.notation_parts
            if len(parts) != len({context.part_index for context in self.source_contexts}):
                raise ValueError("Score matrix lost a source part")
            if sum(len(m.elements) for part in parts for m in part.measures) != len(self.notation_elements):
                raise ValueError("Score matrix lost source notation children")
        elif self.source_contexts or self.notation_elements:
            raise ValueError("Source notation has no original MusicXML")

    @property
    def notation_parts(self) -> tuple[MatrixNotationPart, ...]:
        """Source Part→Measure/Voice hierarchy, including unvoiced annotations."""
        return notation_parts(self.notation_elements, self.source_contexts)

    def context_at_measure(self, part_index: int, measure: int) -> MatrixMeasureContext:
        matches = [context for context in self.source_contexts
                   if (context.part_index, context.measure) == (part_index, measure)]
        if len(matches) != 1:
            raise ValueError("No unique original source measure context")
        return matches[0]

    def source_connectors(self):
        """Explicit written slurs/ties, with unresolved partial-window arcs."""
        from .coda_source_connectors import link_source_connectors
        return link_source_connectors(self.notation_elements)

    def connector_protected_source_ids(self) -> frozenset[str]:
        """Every note under an authored source arc is ineligible for retiming."""
        from .coda_source_connectors import protected_connector_source_ids
        return protected_connector_source_ids(
            self.notation_elements, self.source_connectors())

    def source_voice_elements(self, name: str) -> tuple[MatrixSourceElement, ...]:
        return tuple(item for item in self.notation_elements
                     if item.voice_id == name)

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

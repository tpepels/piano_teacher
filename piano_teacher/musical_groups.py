"""Original-piece musical groups for exercise selection.

These are *attack identities*, never freshly inferred from an already
simplified exercise. The MIDI-only importer supplies the original attacks;
our internal MusicXML compiler provides their complete native beam inventory.
A chord is an attack with multiple possible pitches, not multiple attacks.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .music import Piece, Phrase, source_note_id


@dataclass(frozen=True)
class MusicalGroup:
    kind: str                  # "beam" or "slur"
    onsets: tuple[frozenset[int], ...]  # original piece Note indices

    @property
    def indices(self) -> frozenset[int]:
        return frozenset(index for onset in self.onsets for index in onset)

    @property
    def attack_count(self) -> int:
        return len(self.onsets)


@dataclass
class MusicalGrouping:
    groups: tuple[MusicalGroup, ...]
    # Note instances are retained when a Phrase is sliced into variants.
    index_by_object: dict[int, int]

    def for_phrase(self, phrase: Phrase, hand: str) -> tuple[tuple[str, tuple[frozenset[int], ...]], ...]:
        local = {self.index_by_object[id(note)]: i
                 for i, note in enumerate(phrase.notes)
                 if id(note) in self.index_by_object
                 and (hand == "both" or note.hand == hand)}
        selected = set(local)
        result = []
        for group in self.groups:
            # A partial long slur is a legal section, but a clipped short
            # slur/beam cannot make a valid whole-group simplification.
            present = [frozenset(local[index] for index in onset if index in selected)
                       for onset in group.onsets]
            # A long slur may be divided into contiguous focus passages.
            # Its complete original still returns in the final performance.
            # Preserve the retained fragment as a local melodic unit rather
            # than sampling isolated notes from the middle of the slur.
            fragment = tuple(onset for onset in present if onset)
            if len(fragment) < 2:
                continue
            if group.kind == "beam" and len(fragment) != len(present):
                continue
            result.append((group.kind, fragment))
        return tuple(result)


def _from_sequences(piece: Piece, sequences: list[tuple[str, tuple[str, ...]]]) -> MusicalGrouping:
    by_source = {source_note_id(note, i): i for i, note in enumerate(piece.notes)}
    by_attack = defaultdict(set)
    for i, note in enumerate(piece.notes):
        by_attack[(note.hand, note.track, note.voice, round(note.start, 6))].add(i)
    found = []
    distinct = set()
    for kind, ids in sequences:
        onsets = []
        seen = set()
        for source in ids:
            index = by_source.get(source)
            if index is None:
                continue
            note = piece.notes[index]
            key = note.hand, note.track, note.voice, round(note.start, 6)
            if key in seen:
                continue
            seen.add(key)
            onsets.append((note.start, frozenset(by_attack[key])))
        onsets.sort(key=lambda pair: pair[0])
        atoms = tuple(group for _, group in onsets)
        if len(atoms) < 2:
            continue
        # Do not manufacture multi-hand or temporally unordered articulation.
        if len({piece.notes[next(iter(a))].hand for a in atoms}) != 1:
            continue
        identity = (kind, atoms)
        if identity not in distinct:
            distinct.add(identity)
            found.append(MusicalGroup(kind, atoms))
    return MusicalGrouping(tuple(found), {id(n): i for i, n in enumerate(piece.notes)})


def _midi_groups(piece: Piece) -> list[tuple[str, tuple[str, ...]]]:
    from .notation.lesson import build_lesson_score

    if not piece.bar_boundaries:
        return []
    phrase = Phrase(0, 1, len(piece.bar_boundaries) - 1,
                    piece.bar_boundaries[0], piece.bar_boundaries[-1], piece.notes)
    score = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures, key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes, barlines=piece.barlines)
    root = ET.fromstring(score.musicxml)
    sequences = []
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            open_beams = {}
            for note in measure.findall("note"):
                if note.find("pitch") is None or note.find("chord") is not None:
                    continue
                binding = score.note_bindings.get(note.get("id"))
                if binding is None:
                    continue
                key = note.findtext("voice", "1")
                for mark in note.findall("beam"):
                    if mark.get("number", "1") != "1":
                        continue
                    action = (mark.text or "").strip()
                    if action == "begin":
                        open_beams[key] = [binding["source_id"]]
                    elif action in ("continue", "end") and key in open_beams:
                        open_beams[key].append(binding["source_id"])
                        if action == "end":
                            sequences.append(("beam", tuple(open_beams.pop(key))))
    return sequences


def grouping_for_piece(piece: Piece) -> MusicalGrouping:
    if not piece.bar_boundaries or len(piece.notes) < 2:
        return MusicalGrouping((), {id(n): i for i, n in enumerate(piece.notes)})
    sequences = _midi_groups(piece)
    return _from_sequences(piece, sequences)

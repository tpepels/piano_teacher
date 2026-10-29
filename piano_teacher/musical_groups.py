"""Original-piece musical groups for exercise selection.

These are *attack identities*, never freshly inferred from an already
simplified exercise. MusicXML supplies its authored beams/slurs; MIDI supplies
the exact full-piece beam declarations written by our notation compiler.
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


def _written_groups(piece: Piece) -> list[tuple[str, tuple[str, ...]]]:
    root = ET.fromstring(piece.source_musicxml)
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    sequences = []
    for part_index, part in enumerate(root.findall("part")):
        open_ties = {}
        open_beams = {}
        open_slurs = {}
        voices = defaultdict(list)
        for measure_index, measure in enumerate(part.findall("measure")):
            open_beams.clear()  # beams never cross a barline
            for ordinal, note in enumerate(measure):
                if note.tag != "note" or note.find("pitch") is None or note.find("grace") is not None:
                    continue
                voice = note.findtext("voice", "1")
                staff = note.findtext("staff", "1")
                pitch = note.find("pitch")
                pitch_key = (staff, voice, pitch.findtext("step"),
                             pitch.findtext("alter", "0"), pitch.findtext("octave"))
                ties = {tag.get("type") for tag in note.findall("tie")}
                if not ties:
                    ties = {tag.get("type") for tag in note.findall("notations/tied")}
                new_id = f"xml-p{part_index}-m{measure_index}-e{ordinal}"
                source = open_ties.get(pitch_key) if "stop" in ties else new_id
                if source is None:  # Source importer rejects orphan ties.
                    continue
                if "start" in ties:
                    open_ties[pitch_key] = source
                elif "stop" in ties:
                    open_ties.pop(pitch_key, None)
                timeline = voices[voice]
                timeline.append(source)
                position = len(timeline) - 1
                for mark in note.findall("notations/slur"):
                    number = mark.get("number", "1")
                    key = voice, staff, number
                    action = mark.get("type")
                    if action == "start":
                        open_slurs[key] = position
                    elif action == "stop":
                        start_key = key
                        if start_key not in open_slurs:
                            matches = [k for k in open_slurs
                                       if k[0] == voice and k[2] == number]
                            if len(matches) != 1:
                                continue
                            start_key = matches[0]
                        start = open_slurs.pop(start_key)
                        sequences.append(("slur", tuple(timeline[start:position + 1])))
                if note.find("chord") is not None:
                    continue
                for mark in note.findall("beam"):
                    if mark.get("number", "1") != "1":
                        continue
                    key = voice, staff
                    action = (mark.text or "").strip()
                    if action == "begin":
                        open_beams[key] = [source]
                    elif action in ("continue", "end") and key in open_beams:
                        open_beams[key].append(source)
                        if action == "end":
                            sequences.append(("beam", tuple(open_beams.pop(key))))
    return sequences


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
    if not piece.source_musicxml and (not piece.bar_boundaries or len(piece.notes) < 2):
        return MusicalGrouping((), {id(n): i for i, n in enumerate(piece.notes)})
    sequences = _written_groups(piece) if piece.source_musicxml else _midi_groups(piece)
    return _from_sequences(piece, sequences)

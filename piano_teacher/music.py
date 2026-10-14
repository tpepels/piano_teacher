"""MIDI import and measure-based practice passages; no GUI dependencies."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from collections import defaultdict, deque
from statistics import median
import re
import mido


@dataclass(frozen=True)
class Note:
    start: float  # quarter-note beats from beginning of MIDI
    end: float
    pitch: int
    track: int
    channel: int
    hand: str = "right"


@dataclass(frozen=True)
class Phrase:
    number: int
    first_bar: int
    last_bar: int
    start: float
    end: float
    notes: tuple[Note, ...]


@dataclass(frozen=True)
class Piece:
    title: str
    bpm: int
    notes: tuple[Note, ...]
    phrases: tuple[Phrase, ...]
    split_pitch: int = 60


def note_name(pitch: int) -> str:
    return f"{'C C# D D# E F F# G G# A A# B'.split()[pitch % 12]}{pitch // 12 - 1}"


def _assign_hands(notes: list[Note], names: dict[int, str], split: int) -> list[Note]:
    groups: dict[int, list[int]] = defaultdict(list)
    for note in notes:
        groups[note.track].append(note.pitch)
    ranked = sorted(groups, key=lambda t: median(groups[t]))
    track_hands: dict[int, str] = {}
    for track, name in names.items():
        if re.search(r"(^|\W)(left|lh|mano sinistra)(\W|$)", name, re.I):
            track_hands[track] = "left"
        elif re.search(r"(^|\W)(right|rh|mano destra)(\W|$)", name, re.I):
            track_hands[track] = "right"
    # Two piano tracks are usually left/right, even when each crosses middle C.
    if len(ranked) == 2:
        track_hands.setdefault(ranked[0], "left")
        track_hands.setdefault(ranked[1], "right")
    return [replace(n, hand=track_hands.get(n.track, "left" if n.pitch < split else "right")) for n in notes]


def _bar_boundaries(length: float, changes: list[tuple[float, int, int]]) -> list[float]:
    """Quarter-note bar positions; time-signature changes start a fresh bar."""
    boundaries = [0.0]
    changes = sorted(changes, key=lambda c: c[0])
    if not changes or changes[0][0] != 0:
        changes.insert(0, (0.0, 4, 4))
    position = 0.0
    for i, (begin, numerator, denominator) in enumerate(changes):
        if begin > length:
            break
        if begin > position + 1e-7:
            boundaries.append(begin)
            position = begin
        next_change = changes[i + 1][0] if i + 1 < len(changes) else float("inf")
        bar_len = numerator * 4.0 / denominator
        if bar_len <= 0:
            raise ValueError("Invalid MIDI time signature")
        while position < min(length, next_change) - 1e-7:
            proposed = position + bar_len
            if proposed > next_change + 1e-7:
                position = next_change
            else:
                position = proposed
            if position > boundaries[-1] + 1e-7:
                boundaries.append(position)
    if len(boundaries) < 2:
        boundaries.append(max(1.0, length))
    return boundaries


def _phrases(notes: list[Note], boundaries: list[float], bars_per_phrase: int) -> tuple[Phrase, ...]:
    phrases: list[Phrase] = []
    for bar in range(0, len(boundaries) - 1, bars_per_phrase):
        end_index = min(bar + bars_per_phrase, len(boundaries) - 1)
        start, end = boundaries[bar], boundaries[end_index]
        selected = tuple(n for n in notes if start - 1e-7 <= n.start < end - 1e-7)
        if selected:
            phrases.append(Phrase(len(phrases) + 1, bar + 1, end_index, start, end, selected))
    return tuple(phrases)


def load_midi(path: str | Path, *, split_pitch: int = 60, bars_per_phrase: int = 2) -> Piece:
    if bars_per_phrase < 1:
        raise ValueError("bars_per_phrase must be >= 1")
    midi = mido.MidiFile(str(path))
    if midi.ticks_per_beat <= 0:
        raise ValueError("SMPTE/timecode MIDI files are not supported")
    ticks = midi.ticks_per_beat
    notes: list[Note] = []
    names: dict[int, str] = {}
    changes: list[tuple[float, int, int]] = []
    tempos: list[tuple[int, int]] = []
    for track_idx, track in enumerate(midi.tracks):
        tick = 0
        open_notes: dict[tuple[int, int], deque[int]] = defaultdict(deque)
        for msg in track:
            tick += msg.time
            if msg.type == "track_name":
                names[track_idx] = msg.name
            if msg.type == "time_signature":
                changes.append((tick / ticks, msg.numerator, msg.denominator))
            if msg.type == "set_tempo":
                tempos.append((tick, msg.tempo))
            if msg.type not in ("note_on", "note_off") or msg.channel == 9:
                continue  # percussion is not piano practice material
            key = (msg.channel, msg.note)
            if msg.type == "note_on" and msg.velocity > 0:
                open_notes[key].append(tick)
            elif open_notes[key]:
                start_tick = open_notes[key].popleft()
                if tick > start_tick:
                    notes.append(Note(start_tick / ticks, tick / ticks, msg.note, track_idx, msg.channel))
        for (channel, pitch), starts in open_notes.items():
            for start_tick in starts:
                if tick > start_tick:
                    notes.append(Note(start_tick / ticks, tick / ticks, pitch, track_idx, channel))
    if not notes:
        raise ValueError("No pitched MIDI notes found (drum-only/empty file)")
    initial_tempo = sorted(tempos)[0][1] if tempos and min(t for t, _ in tempos) == 0 else 500000
    bpm = round(60_000_000 / initial_tempo)
    notes = sorted(_assign_hands(notes, names, split_pitch), key=lambda n: (n.start, n.pitch, n.track))
    end = max(n.end for n in notes)
    boundaries = _bar_boundaries(end, changes)
    return Piece(Path(path).stem, bpm, tuple(notes), _phrases(notes, boundaries, bars_per_phrase), split_pitch)


def with_split(piece: Piece, split_pitch: int) -> Piece:
    """Change pitch fallback while retaining automatic named/two-track assignment.

    Reimporting is required to get the original track names. This helper only
    applies to notes assigned using pitch, and is not used by the GUI.
    """
    assigned = [replace(n, hand="left" if n.pitch < split_pitch else "right") for n in piece.notes]
    boundaries = sorted({b for phrase in piece.phrases for b in (phrase.start, phrase.end)})
    return replace(piece, notes=tuple(assigned), phrases=_phrases(assigned, boundaries, 1), split_pitch=split_pitch)


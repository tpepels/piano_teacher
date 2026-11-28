"""MIDI import and measure-based practice passages; no GUI dependencies."""
from __future__ import annotations

from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from collections import defaultdict, deque
from statistics import median
from typing import TYPE_CHECKING
import re
import mido

if TYPE_CHECKING:
    from .fingering.types import FingeringPlan


@dataclass(frozen=True)
class Note:
    start: float  # quarter-note beats from beginning of MIDI
    end: float
    pitch: int
    track: int
    channel: int
    hand: str = "right"
    source_id: str = ""
    voice: str = ""
    spelling: tuple[str, int, int] | None = None
    velocity: int = 85  # Original MIDI attack dynamics for sampled Listen
    written_id: str = ""  # Shared by repeated occurrences of one written note.
    written_note: str = ""  # Original note markup, including authored notations.
    written_divisions: int = 0
    grace_before: str = ""  # Untimed MusicXML note attached to this attack.

    def performance_document(self) -> dict:
        """The performed attack stored in predictions and learner evidence."""
        return {"start": self.start, "end": self.end, "pitch": self.pitch,
                "track": self.track, "channel": self.channel, "hand": self.hand,
                "source_id": self.source_id, "voice": self.voice,
                "spelling": self.spelling, "velocity": self.velocity}


def source_note_id(note: Note, index: int) -> str:
    """Canonical imported attack identity; explicit local legacy fallback."""
    return note.source_id or f"legacy-note-{index}"


@dataclass(frozen=True)
class KeySignature:
    beat: float
    fifths: int
    hand: str = "both"
    mode: str | None = None


@dataclass(frozen=True)
class ClefChange:
    beat: float
    sign: str
    line: int
    octave_change: int = 0
    hand: str = "both"


@dataclass(frozen=True)
class Phrase:
    number: int
    first_bar: int
    last_bar: int
    start: float
    end: float
    notes: tuple[Note, ...]

    @property
    def sounding_end(self) -> float:
        """Release of the selected attacks, independent of authored barlines."""
        return max(self.end, max((note.end for note in self.notes), default=self.end))

    @property
    def first_attack_beat(self) -> float:
        """First selected attack in unchanged, phrase-local source beats."""
        return max(0.0, min((note.start-self.start for note in self.notes), default=0.0))


@dataclass(frozen=True)
class BarlineChange:
    beat: float
    location: str
    style: str
    repeat: str = ""
    ending: dict | None = None


@dataclass(frozen=True)
class Piece:
    title: str
    bpm: int
    notes: tuple[Note, ...]
    phrases: tuple[Phrase, ...]
    split_pitch: int = 60
    bar_boundaries: tuple[float, ...] = ()
    time_signatures: tuple[tuple[float, int, int], ...] = ()
    key_signatures: tuple[KeySignature, ...] = ()
    clef_changes: tuple[ClefChange, ...] = ()
    import_warnings: tuple[str, ...] = ()
    barlines: tuple[BarlineChange, ...] = ()
    # Computed for this complete original piece, never for a lesson variant.
    fingering_plan: FingeringPlan | None = None
    # Explicit import provenance. Generated MusicXML is internal rendering;
    # MIDI input has no authoritative authored notation.
    source_format: str = ""
    midi_ticks_per_beat: int = 0
    # Fingers written in an imported MusicXML score: (source_id, finger).
    authored_fingerings: tuple[tuple[str, int], ...] = ()


def note_name(pitch: int) -> str:
    return f"{'C C# D D# E F F# G G# A A# B'.split()[pitch % 12]}{pitch // 12 - 1}"


def named_hand(name: str) -> str | None:
    if re.search(r"(^|\W)(left|lh|mano sinistra)(\W|$)", name, re.I):
        return "left"
    if re.search(r"(^|\W)(right|rh|mano destra)(\W|$)", name, re.I):
        return "right"
    return None


def assign_hands(notes: list[Note], names: dict[int, str], split: int) -> list[Note]:
    groups: dict[int, list[int]] = defaultdict(list)
    for note in notes:
        groups[note.track].append(note.pitch)
    ranked = sorted(groups, key=lambda t: median(groups[t]))
    track_hands: dict[int, str] = {}
    for track, name in names.items():
        hand = named_hand(name)
        if hand is not None:
            track_hands[track] = hand
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


def phrases_from_notes(notes: list[Note], boundaries: list[float], bars_per_phrase: int) -> tuple[Phrase, ...]:
    phrases: list[Phrase] = []
    for bar in range(0, len(boundaries) - 1, bars_per_phrase):
        end_index = min(bar + bars_per_phrase, len(boundaries) - 1)
        start, end = boundaries[bar], boundaries[end_index]
        selected = tuple(n for n in notes if start - 1e-7 <= n.start < end - 1e-7)
        if selected:
            phrases.append(Phrase(len(phrases) + 1, bar + 1, end_index, start, end, selected))
    return tuple(phrases)


class PerformanceNotes:
    """One FIFO release policy for the historical practice and progress timeline."""

    def __init__(self, ticks_per_beat):
        self.ticks = ticks_per_beat
        self.notes = []
        self.warnings = []
        self.pending = defaultdict(deque)
        self.zero_duration = self.orphan_releases = 0

    def attack(self, note, tick):
        key = note.track, note.channel, note.pitch
        if self.pending[key]:
            self.warnings.append(
                f"Ambiguous overlapping MIDI notes on track {note.track}, "
                f"channel {note.channel}, pitch {note.pitch}: attack "
                f"{note.source_id} at tick {tick}; releases paired "
                "FIFO (oldest attack first). All attack/release times retained; "
                "individual pairing is not uniquely specified by MIDI.")
        self.pending[key].append(note)

    def release(self, track, channel, pitch, tick):
        key = track, channel, pitch
        if key not in self.pending:
            self.orphan_releases += 1
            return
        pending = self.pending[key]
        note = pending.popleft()
        if not pending:
            del self.pending[key]
        end = tick / self.ticks
        if end == note.start:
            self.zero_duration += 1
        elif end < note.start:
            raise ValueError(f"Invalid MIDI event ordering on track {track}, pitch {pitch}")
        else:
            self.notes.append(note if note.end == end else replace(note, end=end))

    def finish(self):
        if self.pending:
            track, channel, pitch = next(iter(self.pending))
            raise ValueError(f"unterminated MIDI note on track {track}, channel {channel}, pitch {pitch}")
        if self.zero_duration:
            self.warnings.append(
                f"Skipped {self.zero_duration} zero-duration MIDI note(s) with no audible length.")
        if self.orphan_releases:
            self.warnings.append(
                f"Ignored {self.orphan_releases} unmatched MIDI note-off event(s).")


def _read_track(messages, track, notes, names, changes, tempos, keys):
    tick = 0
    for ordinal, msg in enumerate(messages):
        tick += msg.time
        if msg.type == "track_name":
            names[track] = msg.name
        elif msg.type == "time_signature":
            changes.append((tick / notes.ticks, msg.numerator, msg.denominator))
        elif msg.type == "set_tempo":
            tempos.append((tick, msg.tempo))
        elif msg.type == "key_signature":
            minor = msg.key.endswith("m")
            key_names = ("Abm Ebm Bbm Fm Cm Gm Dm Am Em Bm F#m C#m G#m D#m A#m" if minor
                         else "Cb Gb Db Ab Eb Bb F C G D A E B F# C#").split()
            keys.append(KeySignature(tick / notes.ticks, key_names.index(msg.key)-7,
                                     mode="minor" if minor else "major"))
        elif msg.type in ("note_on", "note_off") and msg.channel != 9:
            if msg.type == "note_on" and msg.velocity > 0:
                notes.attack(Note(tick/notes.ticks, tick/notes.ticks, msg.note, track, msg.channel,
                    source_id=f"midi-t{track}-e{ordinal}", voice=f"midi-t{track}-c{msg.channel}",
                    velocity=msg.velocity), tick)
            else:
                notes.release(track, msg.channel, msg.note, tick)
    return tick


def load_midi(path: str | Path, *, split_pitch: int = 60, bars_per_phrase: int = 2,
              data: bytes | None = None) -> Piece:
    if bars_per_phrase < 1:
        raise ValueError("bars_per_phrase must be >= 1")
    midi = mido.MidiFile(str(path), file=None if data is None else BytesIO(data))
    if midi.type == 2:
        raise ValueError("Asynchronous MIDI type 2 has no single musical timeline")
    if midi.ticks_per_beat <= 0:
        raise ValueError("SMPTE/timecode MIDI files are not supported")
    ticks = midi.ticks_per_beat
    notes = PerformanceNotes(ticks)
    names, changes, tempos, keys = {}, [], [], []
    end = max((_read_track(messages, track, notes, names, changes, tempos, keys)
               for track, messages in enumerate(midi.tracks)), default=0)
    notes.finish()
    return piece_from_performance(path, notes.notes, names, changes, tempos, keys,
                                 end, ticks, split_pitch, bars_per_phrase, notes.warnings, "midi")


def piece_from_performance(path, notes, names, changes, tempos, keys, source_end_tick,
                          ticks, split_pitch, bars_per_phrase, warnings, source_format):
    """Build the one practice timeline and its historical measure windows."""
    if not notes:
        raise ValueError("No pitched MIDI notes found (drum-only/empty file)")
    # Discard impossible export-only meter spikes while keeping the most
    # recent usable meter. For example, a piano export may insert 131/4
    # for a four-beat passage; that should not redefine its measure grid.
    # Source beats and note events are never shifted by this repair.
    repaired_meters = []
    valid_changes = []
    for beat, numerator, denominator in sorted(set(changes)):
        if numerator > 32 or denominator > 32:
            repaired_meters.append(f"{numerator}/{denominator} at beat {beat:g}")
            continue
        if valid_changes and valid_changes[-1][1:] == (numerator, denominator):
            continue
        valid_changes.append((beat, numerator, denominator))
    changes = valid_changes
    initial_tempo = sorted(tempos)[0][1] if tempos and min(t for t, _ in tempos) == 0 else 500000
    bpm = round(60_000_000 / initial_tempo)
    notes = sorted(assign_hands(notes, names, split_pitch), key=lambda n: (n.start, n.pitch, n.track))
    signatures = {}
    for beat, numerator, denominator in changes:
        if beat in signatures and signatures[beat] != (numerator, denominator):
            raise ValueError(f"conflicting MIDI time signatures at quarter beat {beat}")
        signatures[beat] = numerator, denominator
    key_contexts = {}
    for signature in keys:
        context = signature.fifths, signature.mode
        if signature.beat in key_contexts and key_contexts[signature.beat] != context:
            raise ValueError(f"conflicting MIDI key signatures at quarter beat {signature.beat}")
        key_contexts[signature.beat] = context
    end = max(max(n.end for n in notes), source_end_tick / ticks)
    boundaries = _bar_boundaries(end, changes)
    if repaired_meters:
        warnings.append("Ignored implausible time signature(s): " + ", ".join(repaired_meters) + ".")
    return Piece(Path(path).stem, bpm, tuple(notes), phrases_from_notes(notes, boundaries, bars_per_phrase),
                 split_pitch, tuple(boundaries), tuple(sorted(set(changes))),
                 tuple(sorted(set(keys), key=lambda signature: (signature.beat, signature.fifths))),
                 import_warnings=tuple(warnings),
                 source_format=source_format, midi_ticks_per_beat=ticks)


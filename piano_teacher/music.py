"""MIDI import and measure-based practice passages; no GUI dependencies."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from collections import defaultdict
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
    source_id: str = ""
    voice: str = ""
    spelling: tuple[str, int, int] | None = None
    velocity: int = 85  # Original MIDI attack dynamics for sampled Listen


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


@dataclass(frozen=True)
class BarlineChange:
    beat: float
    location: str
    style: str
    repeat: str = ""


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
    # Original XML is retained, not reconstructed from Note events. It
    # includes direction, articulation, pedal, ornament, slur and grouping
    # elements that timed MIDI notes cannot faithfully represent.
    source_musicxml: str = ""


def note_name(pitch: int) -> str:
    return f"{'C C# D D# E F F# G G# A A# B'.split()[pitch % 12]}{pitch // 12 - 1}"


def _named_hand(name: str) -> str | None:
    if re.search(r"(^|\W)(left|lh|mano sinistra)(\W|$)", name, re.I):
        return "left"
    if re.search(r"(^|\W)(right|rh|mano destra)(\W|$)", name, re.I):
        return "right"
    return None


def _assign_hands(notes: list[Note], names: dict[int, str], split: int) -> list[Note]:
    groups: dict[int, list[int]] = defaultdict(list)
    for note in notes:
        groups[note.track].append(note.pitch)
    ranked = sorted(groups, key=lambda t: median(groups[t]))
    track_hands: dict[int, str] = {}
    for track, name in names.items():
        hand = _named_hand(name)
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
    if midi.type == 2:
        raise ValueError("Asynchronous MIDI type 2 has no single musical timeline")
    if midi.ticks_per_beat <= 0:
        raise ValueError("SMPTE/timecode MIDI files are not supported")
    ticks = midi.ticks_per_beat
    notes: list[Note] = []
    names: dict[int, str] = {}
    changes: list[tuple[float, int, int]] = []
    tempos: list[tuple[int, int]] = []
    keys: list[KeySignature] = []
    source_end_tick = 0
    discarded_zero_duration = 0
    discarded_orphan_releases = 0
    for track_idx, track in enumerate(midi.tracks):
        tick = 0
        open_notes: dict[tuple[int, int], tuple[int, int, int]] = {}
        for ordinal, msg in enumerate(track):
            tick += msg.time
            if msg.type == "track_name":
                names[track_idx] = msg.name
            if msg.type == "time_signature":
                changes.append((tick / ticks, msg.numerator, msg.denominator))
            if msg.type == "set_tempo":
                tempos.append((tick, msg.tempo))
            if msg.type == "key_signature":
                minor = msg.key.endswith("m")
                key_names = ("Abm Ebm Bbm Fm Cm Gm Dm Am Em Bm F#m C#m G#m D#m A#m" if minor
                         else "Cb Gb Db Ab Eb Bb F C G D A E B F# C#").split()
                keys.append(KeySignature(tick / ticks, key_names.index(msg.key)-7,
                                         mode="minor" if minor else "major"))
            if msg.type not in ("note_on", "note_off") or msg.channel == 9:
                continue  # percussion is not piano practice material
            key = (msg.channel, msg.note)
            if msg.type == "note_on" and msg.velocity > 0:
                if key in open_notes:
                    raise ValueError(f"overlapping MIDI note on track {track_idx}, channel {msg.channel}, pitch {msg.note}; use separate voices/channels")
                open_notes[key] = tick, ordinal, msg.velocity
            elif key in open_notes:
                start_tick, attack, attack_velocity = open_notes.pop(key)
                if tick == start_tick:
                    # Some piano MIDI exports contain instantaneous placeholder
                    # note pairs. They have no sounding duration and cannot be
                    # assessed as played notes; dropping only this pair preserves
                    # the real notes and their canonical source identities.
                    discarded_zero_duration += 1
                    continue
                if tick < start_tick:
                    raise ValueError(f"Invalid MIDI event ordering on track {track_idx}, pitch {msg.note}")
                notes.append(Note(start_tick / ticks, tick / ticks, msg.note, track_idx, msg.channel,
                                  source_id=f"midi-t{track_idx}-e{attack}",
                                  voice=f"midi-t{track_idx}-c{msg.channel}",
                                  velocity=attack_velocity))
            else:
                # Many MIDI performance exports include unmatched channel
                # releases from pedal/voice processing. With no corresponding
                # attack they cannot sound or affect a practice exercise.
                discarded_orphan_releases += 1
        if open_notes:
            channel, pitch = next(iter(open_notes))
            raise ValueError(f"unterminated MIDI note on track {track_idx}, channel {channel}, pitch {pitch}")
        source_end_tick = max(source_end_tick, tick)
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
    notes = sorted(_assign_hands(notes, names, split_pitch), key=lambda n: (n.start, n.pitch, n.track))
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
    warnings = []
    if discarded_zero_duration:
        warnings.append(
            f"Skipped {discarded_zero_duration} zero-duration MIDI note(s) with no audible length.")
    if discarded_orphan_releases:
        warnings.append(
            f"Ignored {discarded_orphan_releases} unmatched MIDI note-off event(s).")
    if repaired_meters:
        warnings.append("Ignored implausible time signature(s): " + ", ".join(repaired_meters) + ".")
    return Piece(Path(path).stem, bpm, tuple(notes), _phrases(notes, boundaries, bars_per_phrase),
                 split_pitch, tuple(boundaries), tuple(sorted(set(changes))),
                 tuple(sorted(set(keys), key=lambda signature: (signature.beat, signature.fifths))),
                 import_warnings=tuple(warnings))


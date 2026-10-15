"""Original, repeatable built-in piano warm-ups as standard MIDI files.

MIDI is generated only when selected and kept outside the user's music folder.
Each Type-1 file has named right/left tracks, a meter, tempo and paired note-offs.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import io
import os
import tempfile

import mido

TICKS_PER_BEAT = 480
PREFIX = "warmup:"


@dataclass(frozen=True)
class Warmup:
    slug: str
    title: str
    focus: str
    description: str
    bpm: int
    meter: tuple[int, int]
    bars: int


WARMUPS = (
    Warmup("chords", "Chord Changes", "Triads and inversions",
           "C-G-Am-F block chords, smooth right-hand inversions and steady left-hand roots.", 68, (4, 4), 8),
    Warmup("finger-patterns", "Five-Finger Ladders", "Hanon-inspired coordination",
           "Original even-eighth-note five-finger patterns rising and falling in parallel hands.", 76, (4, 4), 8),
    Warmup("classical-melody", "Classical Melody", "Legato and Alberti bass",
           "Original eight-bar G-major phrase with clear cadences and broken-chord accompaniment.", 64, (3, 4), 8),
    Warmup("pop-accompaniment", "Pop Accompaniment", "Syncopated pop chords",
           "C-G-Am-F with offbeat right-hand chord stabs and root-fifth bass patterns.", 88, (4, 4), 8),
    Warmup("jazz-voicings", "Jazz Chord Voicings", "ii-V-I and ninth/thirteenth colours",
           "Dm9-G13-Cmaj9-Am9 with left-hand roots and syncopated right-hand colour tones.", 66, (4, 4), 8),
    Warmup("jazz-phrasing", "Jazz Phrasing", "Swing eighths and melodic space",
           "Original swung C-major improvisation phrases over a repeating ii-V-I-vi groove.", 72, (4, 4), 8),
)
_BY_SLUG = {w.slug: w for w in WARMUPS}


def catalog() -> list[dict]:
    """Metadata-only listing; never generates MIDI while the library is scanned."""
    return [{"id": PREFIX + w.slug, "title": w.title, "folder": "Warm-ups",
             "format": "Exercise", "focus": w.focus, "description": w.description,
             "bpm": w.bpm, "meter": f"{w.meter[0]}/{w.meter[1]}", "bars": w.bars}
            for w in WARMUPS]


def is_warmup(identifier: str) -> bool:
    return isinstance(identifier, str) and identifier.startswith(PREFIX) and identifier[len(PREFIX):] in _BY_SLUG


def beat(value) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(str(value))


class _Notes:
    def __init__(self, exercise: Warmup):
        self.exercise = exercise
        self.entries: list[tuple[str, Fraction, Fraction, int, int]] = []

    def add(self, hand: str, pitch: int, start, duration, velocity: int = 76) -> None:
        start, duration = beat(start), beat(duration)
        measure_length = Fraction(4 * self.exercise.meter[0], self.exercise.meter[1])
        if (hand not in ("right", "left") or not 21 <= pitch <= 108 or start < 0
                or duration <= 0 or start + duration > self.exercise.bars * measure_length):
            raise ValueError(f"Invalid note in {self.exercise.slug}")
        if (start * TICKS_PER_BEAT).denominator != 1 or (duration * TICKS_PER_BEAT).denominator != 1:
            raise ValueError("Warm-up notes must fit the MIDI tick grid")
        self.entries.append((hand, start, start + duration, pitch, velocity))

    def chord(self, hand: str, pitches, start, duration, velocity: int = 76) -> None:
        for pitch in pitches:
            self.add(hand, pitch, start, duration, velocity)


def _chords(n: _Notes) -> None:
    harmony = [((60, 64, 67), 48, 55), ((59, 62, 67), 43, 50),
               ((60, 64, 69), 45, 52), ((60, 65, 69), 41, 48)]
    for bar in range(8):
        upper, root, fifth = harmony[bar % 4]
        t = bar * 4
        n.chord("right", upper, t, 1.75)
        n.chord("right", upper, t + 2, 1.75, 70)
        n.add("left", root, t, 1.85, 74)
        n.add("left", fifth, t + 2, 1.85, 70)


def _finger_patterns(n: _Notes) -> None:
    # An original repeating five-finger figure, not a copied Hanon étude.
    scale = [48, 50, 52, 53, 55, 57, 59, 60, 62, 64]
    pattern = [0, 1, 2, 3, 4, 3, 2, 1]
    for bar, root in enumerate((0, 1, 2, 3, 3, 2, 1, 0)):
        for step, degree in enumerate(pattern):
            pitch = scale[root + degree]
            start = bar * 4 + Fraction(step, 2)
            n.add("left", pitch, start, Fraction(9, 20), 66)
            n.add("right", pitch + 12, start, Fraction(9, 20), 80)


def _classical_melody(n: _Notes) -> None:
    melody = [
        [(67, 0, 1), (71, 1, .5), (74, 1.5, .5), (72, 2, 1)],
        [(71, 0, 1), (69, 1, .5), (67, 1.5, .5), (69, 2, 1)],
        [(71, 0, 1), (74, 1, 1), (76, 2, 1)],
        [(74, 0, 1), (72, 1, .5), (71, 1.5, .5), (69, 2, 1)],
        [(67, 0, 1), (71, 1, .5), (74, 1.5, .5), (78, 2, 1)],
        [(76, 0, .5), (74, .5, .5), (72, 1, 1), (69, 2, 1)],
        [(71, 0, 1), (69, 1, .5), (66, 1.5, .5), (67, 2, 1)],
        [(67, 0, 2.75)],
    ]
    accompaniment = [(55, 62, 59), (50, 57, 54), (52, 59, 55), (50, 57, 54),
                     (55, 62, 59), (48, 55, 52), (50, 57, 54), (55, 62, 59)]
    for bar, line in enumerate(melody):
        for pitch, offset, length in line:
            n.add("right", pitch, bar * 3 + beat(offset), beat(length) * Fraction(9, 10), 82)
        root, fifth, third = accompaniment[bar]
        for step, pitch in enumerate((root, fifth, third, fifth)):
            n.add("left", pitch, bar * 3 + Fraction(step * 3, 4), Fraction(13, 20), 60)


def _pop(n: _Notes) -> None:
    harmony = [((60, 64, 67), 48, 55), ((59, 62, 67), 43, 50),
               ((60, 64, 69), 45, 52), ((60, 65, 69), 41, 48)]
    for bar in range(8):
        upper, root, fifth = harmony[bar % 4]
        t = bar * 4
        for offset, length, strength in ((0, .8, 72), (1.5, .425, 84),
                                         (2.5, .45, 78), (3.5, .375, 86)):
            n.chord("right", upper, t + beat(offset), beat(length), strength)
        for offset, pitch in ((0, root), (1.5, fifth), (2, root), (3.5, fifth)):
            n.add("left", pitch, t + beat(offset), Fraction(9, 20), 78)


def _jazz_voicings(n: _Notes) -> None:
    # Dm9 / G13 / Cmaj9 / Am9; playable colours without huge hand stretches.
    harmony = [((60, 64, 69), (50, 53)), ((59, 64, 69), (43, 53)),
               ((59, 62, 64, 67), (48, 52)), ((59, 60, 64, 67), (45, 48))]
    for bar in range(8):
        upper, lower = harmony[bar % 4]
        t = bar * 4
        n.chord("left", lower, t, 1.65, 71)
        n.chord("left", lower, t + 2.5, 1.1, 65)
        n.chord("right", upper, t + Fraction(1, 2), 1.2, 76)
        n.chord("right", upper, t + 3, Fraction(4, 5), 68)


def _jazz_phrasing(n: _Notes) -> None:
    # True triplet-swing offbeats and deliberate rests, not equal straight 8ths.
    lines = [
        (62, 65, 69, 72, 69), (67, 71, 74, 77, 76),
        (64, 67, 71, 74, 72), (60, 64, 67, 71, 69),
        (65, 69, 72, 74, 72), (71, 74, 77, 79, 77),
        (72, 71, 67, 64, 62), (60, 64, 67, 64, 60),
    ]
    roots = (50, 43, 48, 45)
    for bar, melody in enumerate(lines):
        t = Fraction(bar * 4)
        n.add("left", roots[bar % 4], t, Fraction(7, 10), 67)
        n.add("left", roots[bar % 4] + 7, t + 2, Fraction(7, 10), 60)
        for offset, pitch, length in zip(
                (Fraction(0), Fraction(2, 3), Fraction(1), Fraction(8, 3), Fraction(3)),
                melody,
                (Fraction(3, 5), Fraction(1, 4), Fraction(9, 10),
                 Fraction(1, 4), Fraction(7, 10))):
            n.add("right", pitch, t + offset, length, 83)


_COMPOSERS = {
    "chords": _chords, "finger-patterns": _finger_patterns,
    "classical-melody": _classical_melody, "pop-accompaniment": _pop,
    "jazz-voicings": _jazz_voicings, "jazz-phrasing": _jazz_phrasing,
}


def render_midi(slug: str) -> bytes:
    """Return a complete, deterministic MIDI file; no external downloads."""
    warmup = _BY_SLUG.get(slug)
    if warmup is None:
        raise ValueError("Unknown built-in warm-up")
    notes = _Notes(warmup)
    _COMPOSERS[slug](notes)
    if {note[0] for note in notes.entries} != {"left", "right"}:
        raise ValueError(f"Warm-up {slug} has an empty hand")
    result = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name", name=warmup.title, time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=warmup.meter[0],
                                 denominator=warmup.meter[1], time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(warmup.bpm), time=0))
    if slug == "classical-melody":
        meta.append(mido.MetaMessage("key_signature", key="G", time=0))
    meta.append(mido.MetaMessage("end_of_track", time=0))
    result.tracks.append(meta)
    for hand, channel in (("right", 0), ("left", 1)):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=f"{hand.title()} Hand", time=0))
        track.append(mido.Message("program_change", channel=channel, program=0, time=0))
        events = []
        for role, start, end, pitch, velocity in notes.entries:
            if role == hand:
                events.append((int(start * TICKS_PER_BEAT), 1, pitch, velocity))
                events.append((int(end * TICKS_PER_BEAT), 0, pitch, 0))
        # Order note-off before note-on at identical timestamps.
        events.sort()
        previous = 0
        for tick, on, pitch, velocity in events:
            track.append(mido.Message("note_on" if on else "note_off", note=pitch,
                                      velocity=velocity, channel=channel, time=tick-previous))
            previous = tick
        track.append(mido.MetaMessage("end_of_track", time=0))
        result.tracks.append(track)
    data = io.BytesIO()
    result.save(file=data)
    return data.getvalue()


def materialize(identifier: str, cache_dir: Path) -> Path:
    """Create a validated built-in MIDI file atomically outside user music."""
    if not is_warmup(identifier):
        raise ValueError("Unknown built-in warm-up")
    cache_dir = Path(cache_dir)
    target = cache_dir / f"{identifier[len(PREFIX):]}.mid"
    content = render_midi(identifier[len(PREFIX):])
    if target.is_file() and target.read_bytes() == content:
        return target
    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".warmup-", suffix=".mid", dir=cache_dir)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return target

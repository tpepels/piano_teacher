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
    Warmup("chords", "Chord Changes", "Simple triads",
           "C-G-Am-F: two half-note chords per bar with alternating bass notes.", 68, (4, 4), 8),
    Warmup("finger-patterns", "Five-Finger Ladders", "Slow finger independence",
           "Original Hanon-inspired five-finger figures, two half notes per bar.", 70, (4, 4), 8),
    Warmup("classical-melody", "Classical Melody", "Melody and accompaniment",
           "Original G-major phrase in 3/4: a half note plus a quarter note per bar.", 64, (3, 4), 8),
    Warmup("pop-accompaniment", "Pop Accompaniment", "Steady pop harmony",
           "C-G-Am-F: half-note chord changes with roots and fifths, no syncopation yet.", 72, (4, 4), 8),
    Warmup("jazz-voicings", "Jazz Chord Voicings", "Simple ii-V-I-vi colours",
           "Dm9-G13-Cmaj9-Am9: compact right-hand voicings in half notes.", 60, (4, 4), 8),
    Warmup("jazz-phrasing", "Jazz Phrasing", "Melodic questions and answers",
           "Easy jazz-influenced two-note phrases, in half notes before swing subdivisions.", 66, (4, 4), 8),
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
        n.chord("right", upper, t, 2)
        n.chord("right", upper, t + 2, 2)
        n.add("left", root, t, 2)
        n.add("left", fifth, t + 2, 2)


def _finger_patterns(n: _Notes) -> None:
    # Slow, original ascending/descending figures (not a copied Hanon étude).
    pitches = [48, 50, 52, 53, 55, 53, 52, 50,
               48, 50, 52, 53, 55, 53, 52, 48]
    for index, pitch in enumerate(pitches):
        for hand, octave in (("left", 0), ("right", 12)):
            n.add(hand, pitch + octave, index * 2, 2)


def _classical_melody(n: _Notes) -> None:
    # In 3/4 one half note followed by a quarter keeps each bar clear.
    melody = [(67, 71), (74, 71), (69, 67), (66, 69),
              (67, 74), (72, 69), (71, 66), (67, 67)]
    bass = [(55, 59), (50, 57), (52, 55), (50, 54),
            (55, 59), (48, 55), (50, 57), (55, 55)]
    for bar in range(8):
        t = bar * 3
        n.add("right", melody[bar][0], t, 2)
        n.add("right", melody[bar][1], t + 2, 1)
        n.add("left", bass[bar][0], t, 2)
        n.add("left", bass[bar][1], t + 2, 1)


def _pop(n: _Notes) -> None:
    harmony = [((60, 64, 67), 48, 55), ((59, 62, 67), 43, 50),
               ((60, 64, 69), 45, 52), ((60, 65, 69), 41, 48)]
    for bar in range(8):
        upper, root, fifth = harmony[bar % 4]
        t = bar * 4
        n.chord("right", upper, t, 2)
        n.chord("right", upper, t + 2, 2)
        n.add("left", root, t, 2)
        n.add("left", fifth, t + 2, 2)


def _jazz_voicings(n: _Notes) -> None:
    harmony = [((65, 72, 76), 50, 57), ((65, 71, 76), 43, 50),
               ((64, 71, 74), 48, 55), ((60, 64, 71), 45, 52)]
    for bar in range(8):
        upper, root, fifth = harmony[bar % 4]
        t = bar * 4
        n.chord("right", upper, t, 2)
        n.chord("right", upper, t + 2, 2)
        n.add("left", root, t, 2)
        n.add("left", fifth, t + 2, 2)


def _jazz_phrasing(n: _Notes) -> None:
    # Questions and answers first; swing and syncopation come in later levels.
    melody = [(62, 65), (67, 71), (64, 67), (60, 64),
              (65, 69), (71, 74), (72, 67), (64, 60)]
    roots = (50, 43, 48, 45)
    for bar, (first, second) in enumerate(melody):
        t = bar * 4
        n.add("right", first, t, 2)
        n.add("right", second, t + 2, 2)
        n.add("left", roots[bar % 4], t, 2)
        n.add("left", roots[bar % 4] + 7, t + 2, 2)


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

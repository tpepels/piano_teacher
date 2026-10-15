"""Source-timed piano examples, streamed into reusable local PCM WAV files.

This module never reads MIDI input or changes lesson progress. The caller owns
playback and transport acknowledgement; rendering only consumes an immutable
active variant and the student's selected BPM.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass
import hashlib
import json
import math
from numbers import Real
import os
from pathlib import Path
import sys
import tempfile
from typing import Iterator
import wave

from .exercise_generator import ExerciseVariant


@dataclass(frozen=True)
class DemoAudio:
    path: Path
    duration_seconds: float
    frame_count: int
    sample_rate: int
    cache_key: str
    instrument: str = "Basic synthesized piano"


@dataclass(frozen=True)
class _Voice:
    first: int
    last: int
    frequency: float


def _finite(value: Real, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _prepare(variant: ExerciseVariant, bpm: Real, sample_rate: int, chunk_frames: int):
    if not isinstance(sample_rate, int) or isinstance(sample_rate, bool) or not 8000 <= sample_rate <= 96000:
        raise ValueError("Audio sample rate must be an integer between 8000 and 96000")
    if not isinstance(chunk_frames, int) or isinstance(chunk_frames, bool) or not 1 <= chunk_frames <= 65536:
        raise ValueError("Audio chunk size must be an integer between 1 and 65536 frames")
    bpm = _finite(bpm, "BPM")
    if not 12 <= bpm <= 300:
        raise ValueError("BPM must be between 12 and 300")
    phrase = variant.phrase
    start, end = _finite(phrase.start, "Phrase start"), _finite(phrase.end, "Phrase end")
    if end <= start:
        raise ValueError("Phrase end must follow its start")
    indices = variant.source_indices
    if (len(indices) != len(variant.notes) or len(set(indices)) != len(indices)
            or any(not isinstance(i, int) or isinstance(i, bool) or i < 0 for i in indices)):
        raise ValueError("Every demo note needs one distinct source index")
    voices = []
    audio_end = end
    for note in variant.notes:
        onset, release = _finite(note.start, "Note onset"), _finite(note.end, "Note release")
        if not start <= onset < end or release <= onset:
            raise ValueError("Note attacks must be inside the source phrase with positive duration")
        if not isinstance(note.pitch, int) or isinstance(note.pitch, bool) or not 0 <= note.pitch <= 127:
            raise ValueError("Source pitch must be an integer MIDI note from 0 to 127")
        frequency = 440 * 2 ** ((note.pitch - 69) / 12)
        if frequency >= sample_rate / 2:
            raise ValueError("Source pitch needs a higher audio sample rate")
        first = round((onset-start)*60/bpm*sample_rate)
        last = max(first+1, round((release-start)*60/bpm*sample_rate))
        voices.append(_Voice(first, last, frequency))
        # Held source notes may cross the last engraved bar. Preserve them.
        audio_end = max(audio_end, release)
    duration = (audio_end-start)*60/bpm
    frames = math.ceil(duration*sample_rate-1e-9)
    if frames <= 0 or frames*2 > 0xffffffff-44:
        raise ValueError("Demo duration exceeds the PCM WAV file range")
    return duration, frames, tuple(sorted(voices, key=lambda voice: voice.first))


def _pcm_chunks(voices: tuple[_Voice, ...], frames: int, sample_rate: int,
                chunk_frames: int) -> Iterator[bytes]:
    concurrency = peak = 0
    for _, change in sorted((at, change) for voice in voices
                            for at, change in ((voice.first, 1), (voice.last, -1))):
        concurrency += change
        peak = max(peak, concurrency)
    gain = .72 / max(1, peak)
    active = []
    next_voice = 0
    for first in range(0, frames, chunk_frames):
        last = min(frames, first+chunk_frames)
        active = [voice for voice in active if voice.last > first]
        while next_voice < len(voices) and voices[next_voice].first < last:
            voice = voices[next_voice]
            if voice.last > first:
                active.append(voice)
            next_voice += 1
        if not active:
            yield bytes((last-first)*2)
            continue
        mixed = [0.0]*(last-first)
        for voice in active:
            duration = (voice.last-voice.first)/sample_rate
            harmonics = [(h, weight) for h, weight in ((1, .8), (2, .15), (3, .05))
                         if voice.frequency*h < sample_rate/2]
            weights = sum(weight for _, weight in harmonics)
            omega = math.tau*voice.frequency
            for frame in range(max(first, voice.first), min(last, voice.last)):
                elapsed = (frame-voice.first)/sample_rate
                envelope = min(1.0, elapsed/.006, (duration-elapsed)/.025)*math.exp(-1.1*elapsed)
                signal = sum(weight*math.sin(omega*h*elapsed) for h, weight in harmonics)/weights
                mixed[frame-first] += gain*envelope*signal
        samples = array('h', (round(max(-1.0, min(1.0, value))*32767) for value in mixed))
        if sys.byteorder != 'little':
            samples.byteswap()
        yield samples.tobytes()


def iter_pcm_chunks(variant: ExerciseVariant, bpm: Real, *, sample_rate: int = 44100,
                    chunk_frames: int = 4096) -> Iterator[bytes]:
    """Yield little-endian mono PCM16, with bounded waveform buffers.

    Time zero is phrase.start. The length includes its final silent bars and
    any source note held past phrase.end. Each yielded chunk has at most
    chunk_frames samples. No whole-passage waveform is allocated.
    """
    _, frames, voices = _prepare(variant, bpm, sample_rate, chunk_frames)
    yield from _pcm_chunks(voices, frames, sample_rate, chunk_frames)


class DemoAudioCache:
    def __init__(self, cache_dir: str | Path, *, sample_rate: int = 44100,
                 chunk_frames: int = 4096):
        self.cache_dir = Path(cache_dir)
        self.sample_rate = sample_rate
        self.chunk_frames = chunk_frames

    def render(self, variant: ExerciseVariant, bpm: Real) -> DemoAudio:
        """Return a reproducible WAV for this exact source variant and BPM."""
        duration, frames, voices = _prepare(variant, bpm, self.sample_rate, self.chunk_frames)
        phrase = variant.phrase
        from .sample_piano import find_soundfont, available, render_wav
        soundfont = find_soundfont()
        if soundfont is not None and not available():
            raise RuntimeError("The sampled piano is installed, but libfluidsynth is missing. Install fluidsynth.")
        content = {
            "synth": 2 if soundfont is not None else 1,
            "bank": soundfont.identity if soundfont else None,
            "sample_rate": self.sample_rate, "bpm": float(bpm),
            "level": variant.level, "range": [phrase.start, phrase.end],
            "source_indices": variant.source_indices,
            "notes": [(n.start, n.end, n.pitch, n.track, n.channel, n.hand,
                       getattr(n, "velocity", 85)) for n in variant.notes],
        }
        key = hashlib.sha256(json.dumps(content, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        path = self.cache_dir/f'{key}.wav'
        result = DemoAudio(path, duration, frames, self.sample_rate, key,
                           soundfont.label if soundfont else "Basic synthesized piano")
        if path.is_file():
            return result
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=f'.{key}.', suffix='.tmp', dir=self.cache_dir)
        try:
            with os.fdopen(handle, 'wb') as output:
                if soundfont is None:
                    with wave.open(output, 'wb') as wav:
                        wav.setnchannels(1)
                        wav.setsampwidth(2)
                        wav.setframerate(self.sample_rate)
                        wav.setnframes(frames)
                        for chunk in _pcm_chunks(voices, frames, self.sample_rate, self.chunk_frames):
                            wav.writeframesraw(chunk)
            if soundfont is not None:
                render_wav(Path(temporary), variant, bpm=float(bpm), frames=frames,
                           sample_rate=self.sample_rate, chunk_frames=self.chunk_frames,
                           soundfont=soundfont)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return result

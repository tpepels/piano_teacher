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
import threading
from typing import Iterator
import wave

from .exercise_generator import ExerciseVariant
from .application.musical_scheduler import SCHEDULER


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
    pitch: int
    velocity: int


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
    if not 1 <= bpm <= 300:
        raise ValueError("BPM must be between 1 and 300")
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
        first = round(SCHEDULER.signed_beats_seconds(onset-start,bpm)*sample_rate)
        last = max(first+1, round(SCHEDULER.signed_beats_seconds(release-start,bpm)*sample_rate))
        voices.append(_Voice(first, last, frequency, note.pitch, getattr(note, "velocity", 85)))
        # Held source notes may cross the last engraved bar. Preserve them.
        audio_end = max(audio_end, release)
    duration = SCHEDULER.signed_beats_seconds(audio_end-start,bpm)
    frames = math.ceil(duration*sample_rate-1e-9)
    if frames <= 0 or frames*2 > 0xffffffff-44:
        raise ValueError("Demo duration exceeds the PCM WAV file range")
    return duration, frames, tuple(sorted(voices, key=lambda voice: voice.first))


def _pcm_chunks(voices: tuple[_Voice, ...], frames: int, sample_rate: int,
                chunk_frames: int, checkpoint) -> Iterator[bytes]:
    concurrency = peak = 0
    for _, change in sorted((at, change) for voice in voices
                            for at, change in ((voice.first, 1), (voice.last, -1))):
        concurrency += change
        peak = max(peak, concurrency)
    # Scale by the square root of the densest chord, not the chord size:
    # dividing by the full note count made every busy passage quiet even
    # where one note sounds alone (owner: Listen "really soft"). Samples are
    # clamped below, so a rare full-voice peak cannot wrap around.
    gain = .72 / max(1.0, math.sqrt(peak))
    sample_seconds = 1.0/sample_rate
    attack_per_frame = sample_seconds/.006
    release_per_frame = sample_seconds/.025
    decay_step = math.exp(-1.1*sample_seconds)
    nyquist = sample_rate/2
    active = []
    next_voice = 0
    for first in range(0, frames, chunk_frames):
        if checkpoint is not None:
            checkpoint()
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
            start = max(first, voice.first)
            stop = min(last, voice.last)
            # Use the same three authentic pitch harmonics with one bounded
            # oscillator. Restart the phase each chunk to bound drift on
            # long sustained notes instead of computing sine three times
            # for each sample of every voice.
            elapsed = (start-voice.first)*sample_seconds
            phase = math.tau*voice.frequency*elapsed
            sine, cosine = math.sin(phase), math.cos(phase)
            step = math.tau*voice.frequency*sample_seconds
            sin_step, cos_step = math.sin(step), math.cos(step)
            second = .15 if voice.frequency*2 < nyquist else 0.0
            third = .05 if voice.frequency*3 < nyquist else 0.0
            inverse_weight = 1.0/(.8+second+third)
            decay = math.exp(-1.1*elapsed)
            for frame in range(start, stop):
                held = frame-voice.first
                remaining = voice.last-frame
                envelope = min(1.0, held*attack_per_frame,
                               remaining*release_per_frame)*decay
                harmonic = (.8*sine + second*(2*sine*cosine)
                            + third*(3*sine-4*sine*sine*sine))*inverse_weight
                mixed[frame-first] += gain*envelope*harmonic
                old_sine = sine
                sine = old_sine*cos_step + cosine*sin_step
                cosine = cosine*cos_step - old_sine*sin_step
                decay *= decay_step
        samples = array('h', (round(max(-1.0, min(1.0, value))*32767) for value in mixed))
        if sys.byteorder != 'little':
            samples.byteswap()
        yield samples.tobytes()


class DemoAudioCache:
    """An on-disk WAV cache with bounded retention.

    Existing and active render keys are protected from eviction. Cache
    cleanup touches only our SHA-256-named .wav files and never temp renders,
    user-provided files or a SoundFont installation.
    """

    DEFAULT_MAX_CACHE_BYTES = 512 * 1024 * 1024
    DEFAULT_MAX_CACHE_FILES = 32

    def __init__(self, cache_dir: str | Path, *, sample_rate: int = 44100,
                 chunk_frames: int = 4096,
                 max_cache_bytes: int = DEFAULT_MAX_CACHE_BYTES,
                 max_cache_files: int = DEFAULT_MAX_CACHE_FILES):
        for name, value in (("max_cache_bytes", max_cache_bytes),
                            ("max_cache_files", max_cache_files)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self.cache_dir = Path(cache_dir)
        self.sample_rate = sample_rate
        self.chunk_frames = chunk_frames
        self.max_cache_bytes = max_cache_bytes
        self.max_cache_files = max_cache_files
        self._lock = threading.Lock()
        self._latest_key = ""
        self._in_flight: dict[str, int] = {}

    def _prune(self) -> None:
        """Evict oldest completed WAVs while preserving in-flight/current.

        The latest requested key remains safe when an older render finishes
        out of order. A single oversized current recording is allowed.
        """
        with self._lock:
            keep = {self._latest_key, *self._in_flight}
            entries: list[tuple[int, str, Path, int]] = []
            try:
                candidates = self.cache_dir.iterdir()
            except FileNotFoundError:
                return
            for candidate in candidates:
                if (candidate.suffix != ".wav" or len(candidate.stem) != 64
                        or any(ch not in "0123456789abcdef" for ch in candidate.stem)
                        or candidate.is_symlink()):
                    continue
                try:
                    info = candidate.stat()
                    if not candidate.is_file():
                        continue
                except OSError:
                    continue
                entries.append((info.st_mtime_ns, candidate.name, candidate, info.st_size))
            total = sum(entry[3] for entry in entries)
            count = len(entries)
            for _, _, candidate, length in sorted(entries):
                if count <= self.max_cache_files and total <= self.max_cache_bytes:
                    break
                if candidate.stem in keep:
                    continue
                try:
                    candidate.unlink()
                except OSError:
                    continue
                total -= length
                count -= 1

    def render(self, variant: ExerciseVariant, bpm: Real, *, checkpoint=None) -> DemoAudio:
        """Return a reproducible WAV for this exact source variant and BPM."""
        duration, frames, voices = _prepare(variant, bpm, self.sample_rate, self.chunk_frames)
        phrase = variant.phrase
        from .sample_piano import find_soundfont, available, render_wav
        soundfont = find_soundfont()
        if soundfont is not None and not available():
            raise RuntimeError("The sampled piano is installed, but libfluidsynth is missing. Install fluidsynth.")
        content = {
            # Bumped when the rendered level changes (3/4: normalised loudness).
            "synth": 3 if soundfont is not None else 5,
            "bank": soundfont.identity if soundfont else None,
            "sample_rate": self.sample_rate, "bpm": float(bpm),
            "level": variant.level, "range": [phrase.start, phrase.end],
            "source_indices": variant.source_indices,
            "notes": [(n.start, n.end, n.pitch, n.track, n.channel, n.hand,
                       getattr(n, "velocity", 85)) for n in variant.notes],
        }
        key = hashlib.sha256(json.dumps(content, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        path = self.cache_dir / f"{key}.wav"
        result = DemoAudio(path, duration, frames, self.sample_rate, key,
                           soundfont.label if soundfont else "Basic synthesized piano")
        with self._lock:
            self._latest_key = key
            self._in_flight[key] = self._in_flight.get(key, 0) + 1
        try:
            if not path.is_file():
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                handle, temporary = tempfile.mkstemp(
                    prefix=f".{key}.", suffix=".tmp", dir=self.cache_dir)
                try:
                    with os.fdopen(handle, "wb") as output:
                        if soundfont is None:
                            with wave.open(output, "wb") as wav:
                                wav.setnchannels(1)
                                wav.setsampwidth(2)
                                wav.setframerate(self.sample_rate)
                                wav.setnframes(frames)
                                for chunk in _pcm_chunks(voices, frames,
                                                        self.sample_rate, self.chunk_frames,
                                                        checkpoint):
                                    wav.writeframesraw(chunk)
                    if soundfont is not None:
                        render_wav(Path(temporary), voices, frames=frames,
                                   sample_rate=self.sample_rate,
                                   chunk_frames=self.chunk_frames, soundfont=soundfont,
                                   checkpoint=checkpoint)
                    if checkpoint is not None:
                        checkpoint()
                    os.replace(temporary, path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                    Path(temporary + ".scaled").unlink(missing_ok=True)
            return result
        finally:
            with self._lock:
                pending = self._in_flight.get(key, 0)
                if pending <= 1:
                    self._in_flight.pop(key, None)
                else:
                    self._in_flight[key] = pending - 1
            self._prune()

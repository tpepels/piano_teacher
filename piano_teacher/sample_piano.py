"""Stereo sampled-piano renderer using libfluidsynth and a local SF2 bank.

A single Note/tempo timeline drives the synth at exact sample boundaries.
The PCM stream is written in chunks: no desktop audio server, network request,
MIDI input, or giant in-memory waveform is required.
"""
from __future__ import annotations

import ctypes as ct
import ctypes.util
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import wave


DEFAULT_SOUNDFONT = Path.home() / ".local/share/piano-teacher/soundfonts/salamander-grand-piano.sf2"


@dataclass(frozen=True)
class SampleBank:
    path: Path
    identity: str
    label: str


def find_soundfont() -> SampleBank | None:
    configured = os.environ.get("PIANO_TEACHER_SOUNDFONT", "").strip()
    path = Path(configured).expanduser() if configured else DEFAULT_SOUNDFONT
    if not path.exists():
        if configured:
            raise FileNotFoundError(f"Configured piano SoundFont does not exist: {path}")
        return None
    if not path.is_file():
        raise ValueError(f"SoundFont is not a regular file: {path}")
    with path.open("rb") as stream:
        header = stream.read(12)
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"sfbk":
        raise ValueError(f"Invalid SF2 SoundFont header: {path}")
    stamp = path.stat()
    identity = f"{path.resolve()}:{stamp.st_size}:{stamp.st_mtime_ns}"
    name = "Salamander Grand Piano (sampled)" if path == DEFAULT_SOUNDFONT else path.stem + " (sampled)"
    return SampleBank(path, identity, name)


def available() -> bool:
    return bool(ct.util.find_library("fluidsynth"))


class _Synth:
    def __init__(self, font: Path, sample_rate: int):
        library_path = ct.util.find_library("fluidsynth")
        if not library_path:
            raise RuntimeError("Sampled piano requires libfluidsynth. Install the fluidsynth package.")
        self.lib = ct.CDLL(library_path)
        self.settings = None
        self.synth = None
        try:
            self._bind()
            self.settings = self.lib.new_fluid_settings()
            if not self.settings:
                raise RuntimeError("Cannot allocate FluidSynth settings")
            self.lib.fluid_settings_setnum(self.settings, b"synth.sample-rate", float(sample_rate))
            self.lib.fluid_settings_setnum(self.settings, b"synth.gain", 0.35)
            self.lib.fluid_settings_setint(self.settings, b"synth.reverb.active", 1)
            self.lib.fluid_settings_setint(self.settings, b"synth.chorus.active", 0)
            self.synth = self.lib.new_fluid_synth(self.settings)
            if not self.synth:
                raise RuntimeError("Cannot initialise FluidSynth")
            # Do not reset all 16 MIDI channels for a piano-only SF2:
            # channel 9 normally requests an absent percussion preset.
            # We select the only channel we render (0) explicitly below.
            sfid = self.lib.fluid_synth_sfload(self.synth, os.fsencode(font), 0)
            if sfid < 0:
                raise RuntimeError(f"FluidSynth could not load the piano SoundFont: {font}")
            if self.lib.fluid_synth_program_select(self.synth, 0, sfid, 0, 0) < 0:
                raise RuntimeError("The piano SoundFont has no playable bank 0 / program 0")
        except BaseException:
            self.close()
            raise

    def _bind(self):
        def bind(name, result, *args):
            fn = getattr(self.lib, name)
            fn.restype = result
            fn.argtypes = list(args)
            return fn
        ptr, integer, number, string = ct.c_void_p, ct.c_int, ct.c_double, ct.c_char_p
        bind("new_fluid_settings", ptr)
        bind("delete_fluid_settings", None, ptr)
        bind("fluid_settings_setnum", integer, ptr, string, number)
        bind("fluid_settings_setint", integer, ptr, string, integer)
        bind("new_fluid_synth", ptr, ptr)
        bind("delete_fluid_synth", None, ptr)
        bind("fluid_synth_sfload", integer, ptr, string, integer)
        bind("fluid_synth_program_select", integer, ptr, integer, integer, integer)
        bind("fluid_synth_noteon", integer, ptr, integer, integer, integer)
        bind("fluid_synth_noteoff", integer, ptr, integer, integer)
        bind("fluid_synth_write_s16", integer, ptr, integer, ptr, integer, integer, ptr, integer, integer)

    def note(self, on: bool, pitch: int, velocity: int = 85):
        if on:
            status = self.lib.fluid_synth_noteon(self.synth, 0, pitch, velocity)
        else:
            status = self.lib.fluid_synth_noteoff(self.synth, 0, pitch)
        if status < 0:
            raise RuntimeError(f"FluidSynth rejected pitch {pitch}")

    def frames(self, count: int) -> bytes:
        # FluidSynth offsets/strides are in signed 16-bit samples, not bytes.
        buffer = ct.create_string_buffer(count * 4)
        result = self.lib.fluid_synth_write_s16(
            self.synth, count, buffer, 0, 2, buffer, 1, 2)
        if result < 0:
            raise RuntimeError("FluidSynth could not render PCM samples")
        return buffer.raw

    def close(self):
        if self.synth is not None:
            self.lib.delete_fluid_synth(self.synth)
            self.synth = None
        if self.settings is not None:
            self.lib.delete_fluid_settings(self.settings)
            self.settings = None


def render_wav(path: Path, variant, *, bpm: float, frames: int,
               sample_rate: int, chunk_frames: int, soundfont: SampleBank) -> None:
    """Render actual recorded grand-piano samples in source clock order."""
    phrase = variant.phrase
    events = []
    for note in variant.notes:
        attack = round((note.start - phrase.start) * 60 / bpm * sample_rate)
        release = max(attack + 1, round((note.end - phrase.start) * 60 / bpm * sample_rate))
        if not 1 <= getattr(note, "velocity", 85) <= 127:
            raise ValueError("Sampled MIDI velocity must be between 1 and 127")
        events.append((attack, 1, note.pitch, int(getattr(note, "velocity", 85))))
        events.append((release, 0, note.pitch, 0))
    events.sort()  # Releases before new attacks at the same tick.
    synth = _Synth(soundfont.path, sample_rate)
    try:
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.setnframes(frames)
            at = index = 0
            while at < frames:
                next_event = events[index][0] if index < len(events) else frames
                if next_event <= at:
                    while index < len(events) and events[index][0] <= at:
                        _, on, pitch, velocity = events[index]
                        synth.note(bool(on), pitch, velocity)
                        index += 1
                    continue
                count = min(chunk_frames, frames - at, next_event - at)
                wav.writeframesraw(synth.frames(count))
                at += count
    finally:
        synth.close()

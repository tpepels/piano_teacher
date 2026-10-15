"""Sampled Listen: real stereo PCM, velocities, phrase clock, cache, safety."""
from __future__ import annotations

import ctypes.util
import io
import math
from pathlib import Path
import struct
import tarfile
import wave

import mido
import pytest

from piano_teacher import demo, sample_piano
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Note, Phrase, load_midi


def source(notes, *, first=0, last=4):
    return ExerciseVariant("original", Phrase(1, 1, 1, first, last, tuple(notes)),
                           tuple(range(len(notes))))


def note(start, end, pitch=60, velocity=85):
    return Note(start, end, pitch, 0, 0, "right", velocity=velocity)


def fake_soundfont(tmp_path):
    path = tmp_path / "sample.sf2"
    path.write_bytes(b"RIFF" + b"\0\0\0\0" + b"sfbk" + b"x" * 256)
    return path


def test_soundfont_selection_rejects_corruption_and_observes_new_install(tmp_path, monkeypatch):
    path = tmp_path / "piano.sf2"
    monkeypatch.setenv("PIANO_TEACHER_SOUNDFONT", str(path))
    with pytest.raises(FileNotFoundError, match="does not exist"):
        sample_piano.find_soundfont()
    path.write_bytes(b"NOT A SOUND FONT")
    with pytest.raises(ValueError, match="Invalid SF2"):
        sample_piano.find_soundfont()
    path.write_bytes(b"RIFF" + b"\0\0\0\0" + b"sfbk" + b"x" * 123)
    first = sample_piano.find_soundfont()
    assert first.path == path and first.label.endswith("(sampled)")
    path.write_bytes(path.read_bytes() + b"extra")
    assert sample_piano.find_soundfont().identity != first.identity


def test_sampled_renderer_writes_exact_stereo_sample_frames_and_midi_events(tmp_path, monkeypatch):
    path = fake_soundfont(tmp_path)
    monkeypatch.setenv("PIANO_TEACHER_SOUNDFONT", str(path))
    monkeypatch.setattr(sample_piano, "available", lambda: True)
    emitted = []

    class FakeSynth:
        def __init__(self, bank, rate):
            assert bank == path and rate == 8000
        def note(self, on, pitch, velocity=85):
            emitted.append(("on" if on else "off", pitch, velocity))
        def frames(self, count):
            return b"\x01\x00\xfe\xff" * count
        def close(self):
            emitted.append(("closed",))

    monkeypatch.setattr(sample_piano, "_Synth", FakeSynth)
    value = source([note(13, 13.5, 60, 42), note(14.5, 15, 64, 109)], first=12, last=16)
    cache = demo.DemoAudioCache(tmp_path / "audio", sample_rate=8000, chunk_frames=193)
    render = cache.render(value, 60)
    assert render.instrument.endswith("(sampled)")
    assert render.frame_count == 32000 and render.duration_seconds == 4
    with wave.open(str(render.path), "rb") as wav:
        assert wav.getnchannels() == 2 and wav.getsampwidth() == 2
        assert wav.getframerate() == 8000 and wav.getnframes() == 32000
        frames = wav.readframes(wav.getnframes())
        assert len(frames) == 32000 * 4
    assert emitted == [("on", 60, 42), ("off", 60, 0),
                       ("on", 64, 109), ("off", 64, 0), ("closed",)]
    before = render.path.stat().st_mtime_ns
    assert cache.render(value, 60).path.stat().st_mtime_ns == before
    assert emitted.count(("closed",)) == 1
    faster = cache.render(value, 120)
    assert faster.frame_count == 16000 and faster.cache_key != render.cache_key
    changed = cache.render(source([note(13, 13.5, 60, 43), note(14.5, 15, 64, 109)],
                                  first=12, last=16), 60)
    assert changed.cache_key != render.cache_key


def test_cache_keeps_basic_fallback_separate_from_sampled(tmp_path, monkeypatch):
    monkeypatch.delenv("PIANO_TEACHER_SOUNDFONT", raising=False)
    monkeypatch.setattr(sample_piano, "DEFAULT_SOUNDFONT", tmp_path / "missing.sf2")
    cache = demo.DemoAudioCache(tmp_path / "audio", sample_rate=8000)
    value = source([note(0, 1)], last=2)
    old = cache.render(value, 80)
    assert old.instrument == "Basic synthesized piano"
    with wave.open(str(old.path), "rb") as wav:
        assert wav.getnchannels() == 1
    path = fake_soundfont(tmp_path)
    monkeypatch.setenv("PIANO_TEACHER_SOUNDFONT", str(path))
    monkeypatch.setattr(sample_piano, "available", lambda: True)
    def sample_file(path, variant, *, bpm, frames, sample_rate, chunk_frames, soundfont):
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b"\x01\0\x01\0" * frames)
    monkeypatch.setattr(sample_piano, "render_wav", sample_file)
    current = cache.render(value, 80)
    assert current.path != old.path and current.instrument.endswith("(sampled)")
    assert current.path.is_file() and old.path.is_file()


def test_velocity_preserved_in_real_midi_import(tmp_path):
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    track.extend([mido.Message("note_on", note=60, velocity=32, time=0),
                  mido.Message("note_off", note=60, velocity=0, time=480),
                  mido.Message("note_on", note=64, velocity=113, time=0),
                  mido.Message("note_off", note=64, velocity=0, time=480)])
    midi.tracks.append(track)
    path = tmp_path / "velocity.mid"
    midi.save(path)
    piece = load_midi(path)
    assert [note.velocity for note in piece.notes] == [32, 113]


def test_real_fluidsynth_sampled_audio_if_system_soundfont_is_available(tmp_path, monkeypatch):
    system = next((p for p in (Path("/usr/share/sounds/sf2/TimGM6mb.sf2"),
                               Path("/usr/share/sounds/sf2/FluidR3_GM.sf2"))
                   if p.is_file()), None)
    if not sample_piano.available() or system is None:
        pytest.skip("A real system SF2 and libfluidsynth are not installed")
    monkeypatch.setenv("PIANO_TEACHER_SOUNDFONT", str(system))
    value = source([note(1, 2, 60, 45), note(2, 3, 64, 114)], last=4)
    audio = demo.DemoAudioCache(tmp_path, sample_rate=16000).render(value, 60)
    with wave.open(str(audio.path), "rb") as wav:
        assert wav.getnchannels() == 2 and wav.getnframes() == 4*16000
        pcm = wav.readframes(wav.getnframes())
    def level(start, end):
        vals = struct.unpack("<" + "h" * ((end-start)*2),
                             pcm[start*4:end*4])
        return max(abs(x) for x in vals)
    assert level(16000 + 2000, 32000) > 100
    assert level(32000 + 2000, 48000) > 100


def test_safe_installer_extracts_only_real_sf2_member(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "install_sf2", Path(__file__).resolve().parents[1] / "scripts/install_piano_soundfont.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    archive = tmp_path / "font.tar.xz"
    file_bytes = b"RIFF" + b"\0\0\0\0" + b"sfbk" + b"z" * (1024*1024)
    with tarfile.open(archive, "w:xz") as tar:
        item = tarfile.TarInfo("Samples/../../instrument.sf2")
        item.size = len(file_bytes)
        tar.addfile(item, io.BytesIO(file_bytes))
    out = tmp_path / "installed" / "piano.sf2"
    installer.install(out, source=archive.as_uri())
    assert out.read_bytes() == file_bytes
    assert "Alexander Holm" in (out.parent / "SALAMANDER-ATTRIBUTION.txt").read_text()
    assert not (tmp_path / "instrument.sf2").exists()
    with pytest.raises(FileExistsError):
        installer.install(out, source=archive.as_uri())

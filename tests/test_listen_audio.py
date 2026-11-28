"""Listen prepares real source PCM and admits only the current ready passage."""
import ctypes.util
from dataclasses import replace
import math
from pathlib import Path
import struct
import wave
from threading import Event

import pytest

from piano_teacher import demo, sample_piano
from piano_teacher.application.listen_session import ListenSelection, ListenSession
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Note, Phrase
from scripts import fetch_countin_voices as voices


def source(notes, *, start=0, end=4):
    notes = tuple(Note(first, last, pitch, 0, 0, "right", f"n{i}")
                  for i, (first, last, pitch) in enumerate(notes))
    return ExerciseVariant("original", Phrase(1, 1, 1, start, end, notes),
                           tuple(range(len(notes))))


@pytest.fixture
def fallback(monkeypatch, tmp_path):
    # Exercise the offline instrument for hosts without FluidSynth.
    monkeypatch.delenv("PIANO_TEACHER_SOUNDFONT", raising=False)
    monkeypatch.setattr(sample_piano, "DEFAULT_SOUNDFONT", tmp_path / "absent.sf2")
    monkeypatch.setattr(sample_piano, "available", lambda: False)


def read_pcm(path):
    with wave.open(str(path), "rb") as wav:
        rate, channels = wav.getframerate(), wav.getnchannels()
        frames = wav.readframes(wav.getnframes())
    return rate, channels, struct.unpack("<" + "h" * (len(frames) // 2), frames)


def test_fallback_pcm_preserves_source_rests_pitch_and_tempo(tmp_path, fallback):
    variant = source([(13, 13.5, 69), (14.5, 15, 76)], start=12, end=16)
    cache = demo.DemoAudioCache(tmp_path, sample_rate=8000)
    slow = cache.render(variant, 60)
    rate, channels, samples = read_pcm(slow.path)
    assert slow.instrument == "Basic synthesized piano"
    assert channels == 1 and rate == 8000 and len(samples) == 32000
    assert not any(samples[:8000]) and any(samples[8200:11800])
    assert not any(samples[12000:20000]) and any(samples[20200:23800])
    assert not any(samples[24000:])
    fast = cache.render(variant, 120)
    _, _, faster = read_pcm(fast.path)
    assert fast.duration_seconds == 2 and len(faster) == 16000
    assert not any(faster[:4000]) and any(faster[4200:5800])
    assert fast.path != slow.path


def test_chord_pcm_contains_both_pitches_and_keeps_release_beyond_last_bar(tmp_path, fallback):
    variant = source([(8, 10, 69), (8, 10, 76)], start=8, end=9)
    audio = demo.DemoAudioCache(tmp_path, sample_rate=8000).render(variant, 60)
    rate, _, samples = read_pcm(audio.path)
    assert audio.duration_seconds == 2 and len(samples) == 16000
    assert any(samples[12000:15000])
    window = samples[800:4000]

    def magnitude(frequency):
        return abs(sum(value * complex(math.cos(math.tau * frequency * i / rate),
                                       math.sin(math.tau * frequency * i / rate))
                       for i, value in enumerate(window)))

    assert magnitude(440) > magnitude(510) * 20
    assert magnitude(659.255) > magnitude(570) * 20


def wait_render(session):
    session.thread.join(timeout=10)
    assert not session.thread.is_alive(), "Listen PCM preparation did not finish"


def test_listen_requires_current_audio_and_score_then_cancel_invalidates_audio(tmp_path, fallback):
    variant = source([(0, 1, 60)])
    selected = ListenSelection(variant, 100, "first", 1, (0, 4), ((0, 4, 4),))
    session = ListenSession(tmp_path)
    token = session.prepare(selected)
    try:
        wait_render(session)
        assert session.snapshot()["audio_available"]
        assert session.begin_playback(1) is None
        assert not session.acknowledge_audio("old-token")
        assert not session.acknowledge_score(0)
        assert session.acknowledge_audio(token)
        assert session.begin_playback(1) is None
        assert session.acknowledge_score(1)
        start = session.begin_playback(1)
        assert start is not None and start.count_in_meter == (4, 4)
        assert session.audio_path(token).is_file()
        session.cancel()
        with pytest.raises(ValueError, match="no longer current"):
            session.audio_path(token)
        replacement = session.prepare(replace(selected, stage_key="second", revision=2))
        wait_render(session)
        assert replacement != token
        assert not session.acknowledge_audio(token)
        assert not session.acknowledge_score(1)
        assert session.acknowledge_audio(replacement) and session.acknowledge_score(2)
        assert session.begin_playback(2) is not None
    finally:
        wait_render(session)
        session.cancel()


def test_failed_audio_write_reports_failure_and_retry_prepares_real_pcm(tmp_path, fallback, monkeypatch):
    cache = demo.DemoAudioCache(tmp_path, sample_rate=8000)
    selected = ListenSelection(source([(0, 1, 60)]), 100, "first", 1, (0, 4), ((0, 4, 4),))
    session = ListenSession(tmp_path, cache=cache)

    def disk_full(*args, **kwargs):
        raise OSError("disk full")

    with monkeypatch.context() as failure:
        failure.setattr(cache, "render", disk_full)
        token = session.prepare(selected)
        wait_render(session)
    assert "disk full" in session.take_failure()
    assert not session.acknowledge_audio(token)
    assert session.begin_playback(1) is None
    current = session.prepare(selected)
    try:
        wait_render(session)
        assert session.snapshot()["audio_available"]
        assert session.acknowledge_audio(current) and session.acknowledge_score(1)
        assert session.begin_playback(1) is not None
    finally:
        session.cancel()


@pytest.mark.parametrize("old_fails", [False,True], ids=["old-audio","old-error"])
def test_late_cancelled_render_cannot_replace_the_current_passage(tmp_path, fallback, old_fails):
    cache = demo.DemoAudioCache(tmp_path, sample_rate=8000)
    entered, release = Event(), Event()
    original_render = cache.render

    def delayed_write(variant, bpm, **options):
        if bpm == 120:
            entered.set()
            assert release.wait(5), "Controlled old audio write was not released"
            if old_fails:
                raise OSError("old passage write failed")
        assert bpm != 90, "A superseded pending passage was rendered"
        return original_render(variant, bpm, **options)

    cache.render = delayed_write
    selected = ListenSelection(source([(0,1,60)]),120,"old",1,(0,4),((0,4,4),))
    session = ListenSession(tmp_path, cache=cache)
    old_token = session.prepare(selected)
    old_worker = session.thread
    try:
        assert entered.wait(5)
        session.cancel()
        session.prepare(replace(selected,bpm=90,stage_key="retired",revision=2))
        current_token = session.prepare(replace(selected,bpm=60,stage_key="current",revision=2))
        assert session.thread is old_worker
        release.set()
        wait_render(session)
        assert session.snapshot()["token"] == current_token
        assert session.snapshot()["audio_available"]
        assert session.take_failure() is None
        assert not session.acknowledge_audio(old_token)
        assert session.acknowledge_audio(current_token) and session.acknowledge_score(2)
        assert session.begin_playback(2) is not None
    finally:
        release.set()
        old_worker.join(5)
        wait_render(session)
        session.cancel()


def test_configured_missing_or_corrupt_soundfont_is_an_error_not_fake_sampled_audio(tmp_path, monkeypatch):
    font = tmp_path / "configured.sf2"
    monkeypatch.setenv("PIANO_TEACHER_SOUNDFONT", str(font))
    cache = demo.DemoAudioCache(tmp_path / "audio", sample_rate=8000)
    variant = source([(0, 1, 60)])
    with pytest.raises(FileNotFoundError):
        cache.render(variant, 100)
    font.write_bytes(b"broken")
    with pytest.raises(ValueError, match="Invalid SF2"):
        cache.render(variant, 100)
    assert not list((tmp_path / "audio").glob("*.wav"))


def test_real_sampled_pcm_when_optional_soundfont_and_library_are_installed(tmp_path, monkeypatch):
    bank = sample_piano.find_soundfont()
    if bank is None:
        system = next((p for p in (Path("/usr/share/sounds/sf2/TimGM6mb.sf2"),
                                   Path("/usr/share/sounds/sf2/FluidR3_GM.sf2"),
                                   Path("/usr/share/soundfonts/FluidR3_GM.sf2")) if p.is_file()), None)
        if system is None:
            pytest.skip("Optional piano SF2 is not installed")
        monkeypatch.setenv("PIANO_TEACHER_SOUNDFONT", str(system))
    if ctypes.util.find_library("fluidsynth") is None:
        pytest.skip("Optional libfluidsynth is not installed")
    audio = demo.DemoAudioCache(tmp_path, sample_rate=16000).render(
        source([(1, 3, 60)], end=2), 60)
    _, channels, pcm = read_pcm(audio.path)
    assert channels == 2 and audio.instrument.endswith("(sampled)")
    assert audio.duration_seconds == 3 and len(pcm) == 3 * 16000 * 2
    assert any(pcm[20000 * 2:45000 * 2])


def test_offline_countin_cache_requires_every_spoken_beat(tmp_path, monkeypatch):
    bundled = Path(__file__).resolve().parents[1] / "godot" / "assets" / "countin"
    monkeypatch.setattr(voices, "DESTINATION", tmp_path)
    for name in voices.SAMPLES:
        (tmp_path / f"{name}.ogg").write_bytes((bundled / f"{name}.ogg").read_bytes())
    assert voices.fetch_samples(offline=True)
    (tmp_path / "shi.ogg").write_bytes(b"partial")
    assert not voices.fetch_samples(offline=True)

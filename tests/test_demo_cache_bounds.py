"""Phase 8E: bounded, safe Listen WAV retention."""
from pathlib import Path
import os
import time

import pytest

from piano_teacher.demo import DemoAudioCache
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Note, Phrase
from piano_teacher import sample_piano


@pytest.fixture(autouse=True)
def synthesized_cache(monkeypatch):
    monkeypatch.setattr(sample_piano, "find_soundfont", lambda: None)


def source(pitch: int) -> ExerciseVariant:
    notes = (Note(0.0, .8, pitch, 0, 0, "right"),)
    return ExerciseVariant("original", Phrase(1, 1, 1, 0, 1, notes), (0,))


def test_cache_limit_removes_oldest_completed_audio_and_keeps_latest(tmp_path):
    cache = DemoAudioCache(tmp_path, sample_rate=8000, max_cache_files=2,
                           max_cache_bytes=1_000_000)
    first = cache.render(source(60), 60)
    second = cache.render(source(62), 60)
    original_mtime = second.path.stat().st_mtime_ns
    again = cache.render(source(62), 60)
    assert again.path == second.path
    assert second.path.stat().st_mtime_ns == original_mtime
    third = cache.render(source(64), 60)
    assert not first.path.exists()
    assert second.path.exists() and third.path.exists()
    assert len(list(tmp_path.glob("*.wav"))) == 2


def test_byte_limit_allows_one_oversized_current_file_without_deleting_it(tmp_path):
    cache = DemoAudioCache(tmp_path, sample_rate=8000,
                           max_cache_bytes=100, max_cache_files=10)
    first = cache.render(source(60), 60)
    assert first.path.stat().st_size > 100
    assert first.path.exists()
    second = cache.render(source(61), 60)
    assert second.path.exists()
    assert not first.path.exists()
    assert len(list(tmp_path.glob("*.wav"))) == 1


def test_eviction_never_touches_unrelated_user_files_temp_renders_or_symlinks(tmp_path):
    foreign = tmp_path / "my-recording.wav"
    foreign.write_bytes(b"preserve me")
    temp = tmp_path / ".render-in-progress.tmp"
    temp.write_bytes(b"temporary")
    outside = tmp_path.parent / "not-our-audio.wav"
    outside.write_bytes(b"outside")
    alias = tmp_path / (("a" * 64) + ".wav")
    try:
        alias.symlink_to(outside)
        has_link = True
    except (OSError, NotImplementedError):
        has_link = False
    cache = DemoAudioCache(tmp_path, sample_rate=8000, max_cache_files=1,
                           max_cache_bytes=100)
    cache.render(source(60), 60)
    cache.render(source(62), 60)
    assert foreign.read_bytes() == b"preserve me"
    assert temp.read_bytes() == b"temporary"
    assert outside.read_bytes() == b"outside"
    if has_link:
        assert alias.is_symlink()
    outside.unlink()


def test_in_flight_render_is_protected_from_cache_cleanup(tmp_path):
    cache = DemoAudioCache(tmp_path, sample_rate=8000, max_cache_files=1,
                           max_cache_bytes=100)
    first = cache.render(source(60), 60)
    with cache._lock:
        cache._in_flight.add(first.cache_key)
    try:
        next_audio = cache.render(source(62), 60)
        assert first.path.exists() and next_audio.path.exists()
    finally:
        with cache._lock:
            cache._in_flight.discard(first.cache_key)
    final_audio = cache.render(source(64), 60)
    assert final_audio.path.exists()
    assert len(list(tmp_path.glob("*.wav"))) == 1


@pytest.mark.parametrize("kwargs", [
    {"max_cache_bytes": 0}, {"max_cache_bytes": True},
    {"max_cache_bytes": -3}, {"max_cache_files": 0},
    {"max_cache_files": 0.5}, {"max_cache_files": False},
])
def test_invalid_cache_caps_fail_early(tmp_path, kwargs):
    with pytest.raises(ValueError, match="positive integer"):
        DemoAudioCache(tmp_path, **kwargs)
    assert list(tmp_path.iterdir()) == []

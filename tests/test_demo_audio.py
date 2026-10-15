"""Listen is a real source-timed audio example, including silence and chords."""
import math
import struct
import tracemalloc
import wave

import pytest

from piano_teacher import demo, sample_piano


@pytest.fixture(autouse=True)
def keep_legacy_waveform_regressions_deterministic(monkeypatch):
    # Existing harmonic-synthesis tests are deliberately about the fallback,
    # even on developers' laptops where Salamander has been installed.
    monkeypatch.setattr(sample_piano, "find_soundfont", lambda: None)

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Note, Phrase


def variant(notes, *, start=0, end=4, indices=None):
    notes = tuple(notes)
    return ExerciseVariant('original', Phrase(1, 1, 2, start, end, notes),
                           tuple(range(len(notes))) if indices is None else indices)


def note(start, end, pitch=69):
    return Note(start, end, pitch, 0, 0, 'right')


def read_pcm(path):
    with wave.open(str(path), 'rb') as stream:
        assert stream.getnchannels() == 1 and stream.getsampwidth() == 2
        frames = stream.readframes(stream.getnframes())
        return stream.getframerate(), struct.unpack('<' + 'h'*(len(frames)//2), frames)


def test_listen_renders_actual_wav_with_source_leading_internal_and_trailing_rests(tmp_path):
    # Absolute beat 12 maps to audio zero; playing both notes continuously is wrong.
    source = variant([note(13, 13.5), note(14.5, 15)], start=12, end=16)
    audio = demo.DemoAudioCache(tmp_path, sample_rate=8000, chunk_frames=257).render(source, 60)
    rate, samples = read_pcm(audio.path)
    assert rate == 8000 and len(samples) == 32000
    assert audio.duration_seconds == 4 and audio.frame_count == 32000
    assert not any(samples[:8000])
    assert max(abs(x) for x in samples[8200:11800]) > 1000
    assert not any(samples[12000:20000])
    assert max(abs(x) for x in samples[20200:23800]) > 1000
    assert not any(samples[24000:])


def test_selected_bpm_scales_attacks_durations_and_silent_phrase_tail(tmp_path):
    source = variant([note(1, 2)], end=4)
    cache = demo.DemoAudioCache(tmp_path, sample_rate=8000)
    slow = cache.render(source, 60)
    fast = cache.render(source, 120)
    _, samples = read_pcm(fast.path)
    assert slow.duration_seconds == 4 and fast.duration_seconds == 2
    assert fast.frame_count == 16000 and fast.path != slow.path
    assert not any(samples[:4000]) and any(samples[4100:7900])
    assert not any(samples[8000:])


def test_polyphonic_example_contains_each_source_pitch_and_preserves_held_release(tmp_path):
    # A4 and E5 have separate fundamentals; phrase.end must not cut off held notes.
    source = variant([note(8, 10, 69), note(8, 10, 76)], start=8, end=9)
    audio = demo.DemoAudioCache(tmp_path, sample_rate=8000).render(source, 60)
    rate, samples = read_pcm(audio.path)
    assert len(samples) == 16000 and audio.duration_seconds == 2
    window = samples[800:4000]

    def magnitude(frequency):
        real = sum(value*math.cos(2*math.pi*frequency*i/rate) for i, value in enumerate(window))
        imag = sum(value*math.sin(2*math.pi*frequency*i/rate) for i, value in enumerate(window))
        return math.hypot(real, imag)

    assert magnitude(440) > magnitude(510)*20
    assert magnitude(659.255) > magnitude(570)*20
    assert any(samples[12000:15000])
    assert max(abs(x) for x in samples) < 32767


def test_cache_uses_exact_source_events_indices_range_and_bpm(tmp_path):
    cache = demo.DemoAudioCache(tmp_path, sample_rate=8000)
    source = variant([note(0, .5, 60)], end=1, indices=(7,))
    original = cache.render(source, 80)
    before = original.path.stat().st_mtime_ns
    again = cache.render(source, 80)
    assert again == original and again.path.stat().st_mtime_ns == before
    alternatives = [
        variant([note(0, .5, 61)], end=1, indices=(7,)),
        variant([note(0, .75, 60)], end=1, indices=(7,)),
        variant([note(.1, .5, 60)], end=1, indices=(7,)),
        variant([note(0, .5, 60)], end=1, indices=(8,)),
        variant([note(0, .5, 60)], end=2, indices=(7,)),
    ]
    assert all(cache.render(other, 80).cache_key != original.cache_key for other in alternatives)
    other_cache = demo.DemoAudioCache(tmp_path/'other', sample_rate=8000, chunk_frames=73)
    assert other_cache.render(source, 80).path.read_bytes() == original.path.read_bytes()


@pytest.mark.parametrize('source,bpm', [
    (variant([note(0, 1, -1)]), 80),
    (variant([note(0, 1, 128)]), 80),
    (variant([note(0, 1, 60.5)]), 80),
    (variant([note(0, 0)]), 80),
    (variant([note(0, math.inf)]), 80),
    (variant([note(math.nan, 1)]), 80),
    (variant([note(-1, 1)]), 80),
    (variant([note(4, 5)]), 80),
    (variant([note(0, 1)], start=2, end=1), 80),
    (variant([note(0, 1)], end=math.inf), 80),
    (variant([note(0, 1)], indices=()), 80),
    (variant([note(0, 1)]), 0),
    (variant([note(0, 1)]), math.nan),
    (variant([note(0, 1)]), 301),
])
def test_invalid_source_or_tempo_fails_before_creating_a_cache_file(tmp_path, source, bpm):
    with pytest.raises(ValueError):
        demo.DemoAudioCache(tmp_path).render(source, bpm)
    assert not list(tmp_path.glob('*.wav'))


def test_low_sample_rate_rejects_unrepresentable_pitch(tmp_path):
    with pytest.raises(ValueError, match='sample rate'):
        demo.DemoAudioCache(tmp_path, sample_rate=8000).render(variant([note(0, 1, 127)]), 80)


def test_held_release_does_not_expand_the_valid_source_attack_range(tmp_path):
    source = variant([note(0, 4), note(2, 3, 72)], end=1)
    with pytest.raises(ValueError, match='inside the source phrase'):
        demo.DemoAudioCache(tmp_path).render(source, 80)


def test_default_format_can_reproduce_the_highest_midi_pitch(tmp_path):
    audio = demo.DemoAudioCache(tmp_path).render(variant([note(0, .1, 127)], end=.1), 120)
    rate, samples = read_pcm(audio.path)
    assert rate == 44100 and len(samples) == 2205 and any(samples)


@pytest.mark.parametrize('options', [
    {'sample_rate': 0}, {'sample_rate': 8000.5}, {'sample_rate': True},
    {'chunk_frames': 0}, {'chunk_frames': 1000000}, {'chunk_frames': 1.5},
])
def test_invalid_stream_format_cannot_create_a_broken_wav(tmp_path, options):
    with pytest.raises(ValueError):
        demo.DemoAudioCache(tmp_path, **options).render(variant([note(0, 1)]), 80)
    assert not list(tmp_path.glob('*.wav'))


def test_full_length_audio_is_produced_in_bounded_chunks_without_a_full_wave_buffer():
    # 237 bars at 30 BPM = 1,896 seconds. A whole float buffer is >60 MB
    # even at this small test sample rate; a streaming render stays <1 MB.
    source = variant([note(0, .25), note(947, 948)], end=948)
    tracemalloc.start()
    count = 0
    for chunk in demo.iter_pcm_chunks(source, 30, sample_rate=8000, chunk_frames=1024):
        assert 0 < len(chunk) <= 2048
        count += len(chunk)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert count == 30336000
    assert peak < 1_000_000

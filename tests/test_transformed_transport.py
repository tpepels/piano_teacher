"""Live timing and Listen WAV share the exercise's exact tempo map."""
from dataclasses import replace
import wave

import pytest

from piano_teacher import sample_piano
from piano_teacher.application.listen_session import ListenSelection, ListenSession
from piano_teacher.demo import DemoAudioCache
from piano_teacher.exercise_contracts import TempoMap, TempoSegment
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import PlayedNote
from piano_teacher.timed_assessment import assess_timed_window


def _selection():
    notes = (
        Note(.5, 1.0, 60, 0, 0, "right", "attack-a"),
        Note(2.5, 3.0, 64, 0, 0, "right", "attack-b"),
    )
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    variant = ExerciseVariant("dotted-long-short+two-phase-tempo", phrase, (0, 1))
    tempo = TempoMap("source-shaped", (
        TempoSegment(0, 2, 30),
        TempoSegment(2, 4, 60),
    ))
    return ListenSelection(variant, 60, "transformed-stage", 7,
                           (0, 4), ((0, 4, 4),), tempo)


def test_listen_audio_matches_transformed_score_tempo_and_source_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(sample_piano, "find_soundfont", lambda: None)
    chosen = _selection()
    session = ListenSession(
        tmp_path, cache=DemoAudioCache(tmp_path/"wav", sample_rate=8000))
    token = session.prepare(chosen)
    session.thread.join(timeout=3)
    assert not session.thread.is_alive()
    info = session.snapshot()
    assert info["audio_available"] and info["duration_seconds"] == pytest.approx(6.0)
    assert info["canonical_source_ids"] == ["attack-a", "attack-b"]
    with wave.open(str(session.audio_path(token)), "rb") as source:
        assert source.getframerate() == 8000
        assert source.getnframes() == 48000
        data = source.readframes(source.getnframes())
        import struct
        samples = struct.unpack("<" + "h" * (len(data)//2), data)
    def peak(left, right):
        return max(abs(v) for v in samples[round(left*8000):round(right*8000)])
    assert peak(0, .95) == 0
    assert peak(1.15, 1.75) > 500
    assert peak(2.3, 4.45) == 0
    assert peak(4.6, 4.95) > 500
    assert peak(5.1, 5.8) == 0

    # Grading operates on the unchanged source notes at precisely the same
    # onsets and releases as the WAV.
    notes = chosen.variant.notes
    played = [
        PlayedNote(note.pitch, chosen.tempo_map.seconds_at(note.start),
                   chosen.tempo_map.seconds_at(note.end))
        for note in notes
    ]
    assert assess_timed_window(
        chosen.variant.phrase, "right", chosen.tempo_map, played).clean
    assert session.acknowledge_audio(token)
    assert session.acknowledge_score(7)
    assert session.begin_playback(7) is not None
    assert not session.finished(now=5.999, run_at=0)
    assert session.finished(now=6, run_at=0)


def test_tempo_map_partial_seek_matches_absolute_note_onsets():
    chosen = _selection()
    map_ = chosen.tempo_map
    local = map_.from_beat(2)
    assert local.seconds_at(2) == pytest.approx(
        map_.seconds_at(4)-map_.seconds_at(2))
    assert local.beat_at(map_.seconds_at(3)-map_.seconds_at(2)) == pytest.approx(1)

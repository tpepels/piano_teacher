"""Listen jobs own audio identity, readiness and asynchronous publication."""
from dataclasses import replace
from threading import Event, RLock

import pytest

from piano_teacher.demo import DemoAudio
from piano_teacher.application.listen_session import ListenSelection, ListenSession
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Note, Phrase


class AudioCache:
    def __init__(self, path):
        self.path = path
        self.calls = []

    def render(self, variant, bpm):
        self.calls.append((variant, bpm))
        return DemoAudio(self.path, 5.0 if bpm == 120 else 10.0, 40000, 8000, "source-audio")


def owner(tmp_path, *, cache=None, lock=None):
    notes = (Note(0, 1, 60, 0, 0, "right", "source-1"),
             Note(4, 10, 64, 0, 0, "right", "source-2"))
    variant = ExerciseVariant("original", Phrase(1, 1, 2, 0, 8, notes), (3, 9))
    selection = ListenSelection(variant=variant, bpm=120, stage_key="selected-stage",
        revision=7, bar_boundaries=(0, 4, 8), time_signatures=((0, 4, 4),))
    cache = cache or AudioCache(tmp_path/"example.wav")
    return ListenSession(tmp_path, cache=cache, lock=lock), selection


def finish(session):
    session.thread.join(3)
    assert not session.thread.is_alive(), "audio publication did not finish"


def test_render_runs_outside_application_lock_and_publishes_only_after_it_is_released(tmp_path):
    entered = Event()
    lock = RLock()

    class Cache(AudioCache):
        def render(self, variant, bpm):
            entered.set()
            return super().render(variant, bpm)

    session, selected = owner(tmp_path, cache=Cache(tmp_path/"audio.wav"), lock=lock)
    with lock:
        token = session.prepare(selected)
        assert entered.wait(1), "rendering must not acquire the application lock"
        initial = session.snapshot()
        assert initial == {
            "token": token, "url": "", "audio_available": False,
            "instrument": "Preparing piano audio", "duration_seconds": 5.0,
            "ready": False, "stage_key": "selected-stage",
            "source_ids": ["selected-stage:3", "selected-stage:9"],
            "canonical_source_ids": ["source-1", "source-2"],
        }
    finish(session)
    available = session.snapshot()
    assert available["audio_available"] and available["url"] == f"/demo.wav?token={token}"
    assert available["duration_seconds"] == 5 and available["sampled"] is False
    assert session.audio_path(token) == tmp_path/"audio.wav"


@pytest.mark.parametrize("audio_first", (False, True))
def test_both_readiness_gates_are_revision_and_token_bound_and_consumed_once(tmp_path, audio_first):
    session, selected = owner(tmp_path)
    token = session.prepare(selected)
    finish(session)
    assert session.begin_playback(7) is None
    assert not session.acknowledge_audio("obsolete")
    assert not session.acknowledge_score(6)
    if audio_first:
        assert session.acknowledge_audio(token)
    else:
        assert session.acknowledge_score(7)
    assert session.begin_playback(7) is None
    if audio_first:
        assert session.acknowledge_score(7)
    else:
        assert session.acknowledge_audio(token)
    assert session.begin_playback(6) is None
    start = session.begin_playback(7)
    assert start.count_in_beats == 4 and start.count_in_bar_beats == 4
    assert start.count_in_meter == (4, 4) and start.delay_seconds == 2
    assert not session.finished(now=104.999, run_at=100)
    assert session.finished(now=105, run_at=100)
    session.acknowledge_audio(token)
    session.acknowledge_score(7)
    assert session.begin_playback(7) is None


def test_score_retarget_keeps_current_pcm_and_requires_the_new_score_ack(tmp_path):
    entered, release = Event(), Event()

    class Cache(AudioCache):
        def render(self, variant, bpm):
            entered.set()
            assert release.wait(3)
            return super().render(variant, bpm)

    session, selected = owner(tmp_path, cache=Cache(tmp_path/"audio.wav"))
    token = session.prepare(selected)
    try:
        assert entered.wait(1)
        assert session.acknowledge_score(7)
        assert not session.acknowledge_audio(token)
        session.retarget_score(8)
    finally:
        release.set()
        finish(session)
    assert session.snapshot()["token"] == token and session.snapshot()["audio_available"]
    assert session.acknowledge_audio(token)
    assert session.begin_playback(7) is None and session.begin_playback(8) is None
    assert not session.acknowledge_score(7)
    assert session.acknowledge_score(8)
    assert session.begin_playback(8) is not None


@pytest.mark.parametrize("obsolete_fails", (False, True))
def test_cancelled_render_cannot_replace_a_new_job_or_publish_a_stale_error(tmp_path, obsolete_fails):
    entered, release = Event(), Event()

    class Cache(AudioCache):
        def render(self, variant, bpm):
            if bpm == 120:
                entered.set()
                assert release.wait(3)
                if obsolete_fails:
                    raise OSError("obsolete render failure")
            return super().render(variant, bpm)

    session, selected = owner(tmp_path, cache=Cache(tmp_path/"audio.wav"))
    old_token = session.prepare(selected)
    old_thread = session.thread
    try:
        assert entered.wait(1)
        session.cancel()
        assert session.snapshot() is None
        with pytest.raises(ValueError, match="no longer current"):
            session.audio_path(old_token)
        current_token = session.prepare(replace(selected, bpm=60, revision=8))
        finish(session)
        current = session.snapshot()
        assert current_token != old_token and current["duration_seconds"] == 10
    finally:
        release.set()
        old_thread.join(3)
    assert not old_thread.is_alive()
    assert session.snapshot() == current and session.take_failure() is None
    assert not session.acknowledge_audio(old_token)


def test_failed_render_is_honest_and_cannot_be_acknowledged_or_served(tmp_path):
    class Cache:
        def render(self, variant, bpm):
            raise OSError("controlled unavailable cache")

    session, selected = owner(tmp_path, cache=Cache())
    token = session.prepare(selected)
    finish(session)
    failed = session.snapshot()
    message = "Listen audio could not be prepared: controlled unavailable cache"
    assert failed["error"] == message and not failed["audio_available"] and failed["url"] == ""
    assert session.take_failure() == message and session.take_failure() is None
    assert not session.acknowledge_audio(token) and not session.acknowledge_score(7)
    assert session.begin_playback(7) is None
    with pytest.raises(ValueError, match="no longer current"):
        session.audio_path(token)
    session.cancel()
    assert session.snapshot() is None and session.take_failure() is None


def test_snapshots_do_not_expose_mutable_job_metadata(tmp_path):
    session, selected = owner(tmp_path)
    token = session.prepare(selected)
    finish(session)
    snapshot = session.snapshot()
    snapshot["source_ids"].clear()
    snapshot["canonical_source_ids"][0] = "another-note"
    snapshot["token"] = "obsolete"
    current = session.snapshot()
    assert current["token"] == token
    assert current["source_ids"] == ["selected-stage:3", "selected-stage:9"]
    assert current["canonical_source_ids"] == ["source-1", "source-2"]


def test_pickup_prepares_using_immediately_following_source_meter(tmp_path):
    session, selected = owner(tmp_path)
    note = Note(.5, 1, 60, 0, 0, "right", "pickup-source")
    phrase = Phrase(1, 1, 2, 0, 4.5, (note,))
    selected = replace(selected, bpm=40,
        variant=ExerciseVariant("original", phrase, (0,)),
        bar_boundaries=(0, .5, 4.5), time_signatures=((0, 1, 8), (.5, 4, 4)))
    token = session.prepare(selected)
    finish(session)
    session.acknowledge_audio(token)
    session.acknowledge_score(7)
    start = session.begin_playback(7)
    assert start.count_in_meter == (4, 4) and start.count_in_bar_beats == 4
    assert start.count_in_beats == 2.5 and start.delay_seconds == 3.75
    assert selected.variant.phrase.end == 4.5 and selected.bar_boundaries == (0, .5, 4.5)

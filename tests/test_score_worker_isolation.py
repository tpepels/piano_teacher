"""Source-bound preparation while the real engine still receives MIDI."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from piano_teacher.inprocess import INVALID


def identity(state):
    return {
        "fingerprint": state["piece_fingerprint"],
        "revision": state["revision"],
        "stage_key": state["stage_key"],
        "hand": state["hand"],
    }


def test_stale_bundle_request_is_rejected_before_engraving(practice_session):
    session = practice_session(bars=3)
    stale = identity(session.snapshot())
    session.select(2, 2)
    code, response = session.commands.request("score.bundle", json.dumps(stale))
    assert code == INVALID
    assert "superseded before" in json.loads(response)["error"]
    current = identity(session.snapshot())
    assert session.ask("score.bundle", **current)["revision"] == current["revision"]


@pytest.mark.parametrize("change", ["navigate", "stop", "replace"])
def test_retired_bundle_cannot_publish(practice_session, monkeypatch, change):
    session = practice_session(bars=3)
    expected = identity(session.snapshot())
    supervisor = session.engine.score_read.process
    supervisor.cache.mkdir(parents=True)
    peer = Path(__file__).parent / "fixtures" / "score_worker_peer.py"
    marker = supervisor.cache / "hang"

    with monkeypatch.context() as patch, ThreadPoolExecutor(1) as executor:
        patch.setattr(supervisor, "worker_args", (str(peer), "hang"))
        result = executor.submit(
            session.commands.request, "score.bundle", json.dumps(expected))
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.005)
            assert marker.exists(), "The subprocess never received the score request"
            inputs = session.snapshot()["midi_input_count"]
            session.strike(72)
            session.tick()
            assert session.snapshot()["midi_input_count"] == inputs + 1
            if change == "navigate":
                session.select(2, 2)
            elif change == "stop":
                session.command("stop")
            else:
                from session_inputs import write_midi
                replacement = write_midi(Path(session.music) / "replacement.mid", bars=3, bpm=100)
                session.ask("library.open", id=replacement.name)
        except BaseException:
            supervisor.close()
            raise
        code, response = result.result(5)
    assert code == INVALID
    assert "superseded during" in json.loads(response)["error"]
    current = identity(session.snapshot())
    assert session.ask("score.bundle", **current)["revision"] == current["revision"]

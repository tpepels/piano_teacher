"""Exercise source-bound asset preparation under deliberate concurrency."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from piano_teacher.application.score_artifact_registry import ScoreArtifactRegistry
from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.inprocess import INVALID


def test_retiring_artifacts_does_not_wait_for_old_engraving():
    old = ScoreArtifacts(None)
    registry = ScoreArtifactRegistry(old)
    entered, release = Event(), Event()

    def engrave():
        with old._engraving_lock:
            entered.set()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=2) as workers:
        active = workers.submit(engrave)
        try:
            assert entered.wait(5)
            retired = workers.submit(registry.invalidate)
            retired.result(timeout=1)
            assert registry.current is not old
            with pytest.raises(ValueError, match="superseded"):
                old.require_active()
        finally:
            release.set()
        active.result(timeout=5)


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


def test_source_navigation_rejects_inflight_bundle(practice_session, monkeypatch):
    session = practice_session(bars=3)
    expected = identity(session.snapshot())
    old = session.engine.score.current_artifacts
    entered, release = Event(), Event()

    def blocked_bundle(_selected):
        with old._engraving_lock:
            entered.set()
            assert release.wait(5)
            return {"revision": expected["revision"]}

    monkeypatch.setattr(old, "bundle", blocked_bundle)
    with ThreadPoolExecutor(max_workers=2) as workers:
        active = workers.submit(
            session.commands.request, "score.bundle", json.dumps(expected)
        )
        try:
            assert entered.wait(5)
            navigation = workers.submit(session.select, 2, 2)
            navigation.result(timeout=3)
            assert session.snapshot()["revision"] != expected["revision"]
            assert session.engine.score.current_artifacts is not old
            with pytest.raises(ValueError, match="superseded"):
                old.require_active()
        finally:
            release.set()
        status, response = active.result(timeout=5)
    assert status == INVALID
    assert "superseded during" in json.loads(response)["error"]


def test_navigation_cannot_wait_for_retired_model_lock(practice_session):
    session = practice_session(bars=3)
    first = identity(session.snapshot())
    old = session.engine.score.current_artifacts
    entered, release = Event(), Event()

    def hold_model():
        with old._model_lock:
            entered.set()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=2) as workers:
        held = workers.submit(hold_model)
        try:
            assert entered.wait(5)
            navigation = workers.submit(session.select, 2, 2)
            navigation.result(timeout=3)
            assert identity(session.snapshot()) != first
            assert session.engine.score.current_artifacts is not old
        finally:
            release.set()
        held.result(timeout=5)


def test_warm_snapshot_does_not_wait_for_current_model_projection(practice_session):
    session = practice_session(bars=3)
    first = identity(session.snapshot())
    assets = session.engine.score.current_artifacts
    entered, release = Event(), Event()

    def hold_projection():
        with assets._model_lock:
            entered.set()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=2) as workers:
        held = workers.submit(hold_projection)
        try:
            assert entered.wait(5)
            snapshot = workers.submit(session.snapshot)
            assert identity(snapshot.result(timeout=2)) == first
            assert session.engine.score.current_artifacts is assets
        finally:
            release.set()
        held.result(timeout=5)

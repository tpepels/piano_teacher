"""Two-stage lookahead is bounded, nonblocking and source-identity-safe."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace
from threading import Event

from piano_teacher.application import future_score as module


def _selection(piece, number):
    return SimpleNamespace(
        identity=(id(piece), number), piece=piece,
        fingerprint=f"piece-{id(piece)}", stage_key=f"stage-{number}",
        hand="both", revision=number)


def _ready(event, selection, timeout=2):
    start = time.monotonic()
    while not event.ready(selection) and time.monotonic() - start < timeout:
        time.sleep(.002)
    assert event.ready(selection), f"Preloading failed for {selection.stage_key}"


def test_two_next_scores_are_bounded_and_pre_serialized(tmp_path, monkeypatch):
    class Geometry:
        def __init__(self, cache):
            self.cache = cache

        def geometry(self, selected):
            return {"anchors": [selected.stage_key]}

        def semantic_score(self, selected):
            return {"notes": [selected.stage_key]}

    monkeypatch.setattr(module, "ScoreArtifacts", Geometry)
    monkeypatch.setattr(module, "PreprocessingCache", lambda root: root)
    piece = object()
    stage2, stage3, stage4 = (
        _selection(piece, number) for number in (2, 3, 4))
    future = module.FutureScore(tmp_path)
    assert json.loads(future.ensure(stage2, number=2, label="Right hand"))[
        "status"] in ("preparing", "ready")
    future.warm(stage3, number=3, label="Left hand")
    _ready(future, stage2)
    _ready(future, stage3)
    assert future.ready(stage2) and future.ready(stage3)
    got = json.loads(future.ensure(stage2, number=2, label="Right hand"))
    assert got["status"] == "ready"
    assert got["layout"]["anchors"] == ["stage-2"]
    assert got["model"]["notes"] == ["stage-2"]
    assert future.adopt(stage3) is not None
    future.warm(stage4, number=4, label="Both hands")
    _ready(future, stage4)
    assert len(future._ready) == 2
    assert not future.ready(stage2)
    assert future.ready(stage3) and future.ready(stage4)


def test_switching_source_drops_stale_in_flight_native_bundle(tmp_path, monkeypatch):
    blocked = Event()
    release = Event()

    class Geometry:
        def __init__(self, cache):
            pass

        def geometry(self, selected):
            if selected.fingerprint == first.fingerprint:
                blocked.set()
                assert release.wait(timeout=2)
            return {"anchors": [selected.fingerprint]}

        def semantic_score(self, selected):
            return {"notes": [selected.fingerprint]}

    monkeypatch.setattr(module, "ScoreArtifacts", Geometry)
    monkeypatch.setattr(module, "PreprocessingCache", lambda root: root)
    first = _selection(object(), 2)
    second = _selection(object(), 2)
    future = module.FutureScore(tmp_path)
    future.ensure(first, number=2, label="Old")
    assert blocked.wait(timeout=1)
    future.ensure(second, number=2, label="New")
    release.set()
    _ready(future, second)
    assert not future.ready(first)
    assert future.adopt(first) is None
    reply = json.loads(future.ensure(second, number=2, label="New"))
    assert reply["fingerprint"] == second.fingerprint
    assert reply["layout"]["anchors"] == [second.fingerprint]


def _await_failure(future, selection, count):
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        with future._guard:
            failed = future._errors.get(selection.identity)
        if failed is not None and failed[1] == count:
            return failed
        time.sleep(.002)
    raise AssertionError(f"Missing preparation failure {count}")


def test_future_score_retries_transient_native_failures_without_losing_stage(tmp_path, monkeypatch):
    clock = [100.0]

    class Flaky:
        attempts = 0
        def __init__(self, cache):
            pass
        def geometry(self, selected):
            Flaky.attempts += 1
            if Flaky.attempts <= 2:
                raise RuntimeError("temporary Verovio preparation failure")
            return {"ready": selected.stage_key}
        def semantic_score(self, selected):
            return {"notes": [selected.stage_key]}

    monkeypatch.setattr(module, "ScoreArtifacts", Flaky)
    monkeypatch.setattr(module, "PreprocessingCache", lambda root: root)
    selection = _selection(object(), 2)
    future = module.FutureScore(tmp_path, clock=lambda: clock[0])
    for attempt in (1, 2):
        assert json.loads(future.ensure(
            selection, number=2, label="Next"))["status"] == "preparing"
        error, count, due = _await_failure(future, selection, attempt)
        assert "temporary Verovio" in error and count == attempt
        assert future.failure(selection) is None
        assert due > clock[0]
        clock[0] = due + .01
    future.ensure(selection, number=2, label="Next")
    _ready(future, selection)
    assert Flaky.attempts == 3
    assert future.failure(selection) is None
    assert json.loads(future.ensure(
        selection, number=2, label="Next"))["status"] == "ready"


def test_future_score_exhaustion_returns_explicit_error_without_fake_ink(tmp_path, monkeypatch):
    clock = [100.0]

    class Broken:
        def __init__(self, cache):
            pass
        def geometry(self, selected):
            raise ValueError("unengraveable authentic notation")
        def semantic_score(self, selected):
            raise AssertionError("geometry failed first")

    monkeypatch.setattr(module, "ScoreArtifacts", Broken)
    monkeypatch.setattr(module, "PreprocessingCache", lambda root: root)
    selection = _selection(object(), 2)
    future = module.FutureScore(tmp_path, clock=lambda: clock[0])
    for attempt in (1, 2, 3):
        future.ensure(selection, number=2, label="Next")
        error, count, due = _await_failure(future, selection, attempt)
        assert count == attempt and "unengraveable" in error
        clock[0] = due + .01
    assert future.failure(selection) == "ValueError: unengraveable authentic notation"
    assert not future.ready(selection)
    assert future.adopt(selection) is None
    reply = json.loads(future.ensure(selection, number=2, label="Next"))
    assert reply["status"] == "error" and "unengraveable" in reply["error"]

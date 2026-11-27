"""Worker failures are visible and the next current score can still load."""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from piano_teacher.application.score_process import ScoreCancelled, ScoreProcess

BINDING = {"fingerprint": "source", "revision": 3, "stage_key": "stage", "hand": "right"}
PEER = Path(__file__).parent / "fixtures" / "score_worker_peer.py"


def peer(path, mode):
    return ScoreProcess(path, executable=sys.executable, worker_args=(str(PEER), mode))


def request(process, payload=b"{}", **kwargs):
    status, response = process.request(
        "score.bundle", BINDING, lambda _: payload, **kwargs)
    assert status == 0
    return json.loads(response)


def running_peer(work, mode):
    marker = work / mode
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if marker.exists() and (pid := marker.read_text()):
            return int(pid)
        time.sleep(.005)
    pytest.fail("The real worker did not receive its framed request")


@pytest.mark.parametrize("fault", ["crash", "malformed", "invalid-json", "checksum", "wrong-id",
                                   "wrong-source", "future-id"])
def test_worker_restarts_and_returns_the_original_requested_result(tmp_path, fault):
    process = peer(tmp_path, fault)
    try:
        first = request(process, generation=4)
        second = request(process, generation=5)
        assert first["pid"] == second["pid"] != os.getpid()
        assert second["id"] > first["id"]
    finally:
        process.close()
    with pytest.raises(ProcessLookupError):
        os.kill(first["pid"], 0)


def test_duplicate_response_cannot_answer_the_next_generation(tmp_path):
    process = peer(tmp_path, "duplicate")
    try:
        first = request(process, generation=11)
        second = request(process, generation=12)
        assert second["id"] == first["id"] + 1
        assert second["pid"] != first["pid"]
    finally:
        process.close()


def test_only_current_detached_rejection_retires_the_worker(tmp_path):
    process = peer(tmp_path, "healthy")
    try:
        first = request(process, generation=3)
        second = request(process, generation=4, rejected_generation=2)
        third = request(process, generation=5, rejected_generation=4)
        assert first["pid"] == second["pid"] != third["pid"]
    finally:
        process.close()


def test_hung_worker_reaps_on_deadline_and_next_retry_recovers(tmp_path):
    process = peer(tmp_path, "hang")
    try:
        with pytest.raises(TimeoutError, match="deadline"):
            request(process, timeout=1)
        old = running_peer(tmp_path, "hang")
        with pytest.raises(ProcessLookupError):
            os.kill(old, 0)
        assert request(process)["pid"] != old
    finally:
        process.close()


def test_cancellation_before_and_during_generation_with_backpressure(tmp_path):
    process = peer(tmp_path, "hang")
    stop = Event()
    stop.set()
    try:
        with pytest.raises(ScoreCancelled):
            request(process, cancelled=stop.is_set)
        assert not (tmp_path / "hang").exists()
        stop.clear()
        with ThreadPoolExecutor(1) as executor:
            active = executor.submit(request, process, cancelled=stop.is_set)
            old = running_peer(tmp_path, "hang")
            try:
                with pytest.raises(RuntimeError, match="busy"):
                    request(process)
            finally:
                stop.set()
            with pytest.raises(ScoreCancelled):
                active.result(timeout=2)
        assert request(process, generation=2)["pid"] != old
    finally:
        process.close()


def test_repeated_startup_shutdown_and_multimegabyte_transfer(tmp_path):
    payload = b"{\"" + b"a" * (4 * 1024 * 1024) + b"\":0}"
    for cycle in range(3):
        work = tmp_path / str(cycle)
        work.mkdir()
        process = peer(work, "large")
        try:
            reply = request(process, payload)
            assert reply["bytes"] == len(payload)
            assert len(reply["data"]) == len(payload)
            assert request(process)["pid"] == reply["pid"]
        finally:
            process.close()
        with pytest.raises(ProcessLookupError):
            os.kill(reply["pid"], 0)
        with pytest.raises(ScoreCancelled):
            request(process)

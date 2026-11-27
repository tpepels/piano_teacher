"""Supervise one notation child. Calls belong to the asset lane."""

import os
import signal
import socket
import sys
import time
from contextlib import suppress
from pathlib import Path
from threading import Event, Lock

from .score_ipc import (
    DEADLINE_SECONDS,
    METADATA_LIMIT,
    REPLY_LIMIT,
    REQUEST_LIMIT,
    VERSION,
    ScoreChannel,
    ScoreProtocolError,
    check_payload,
    check_request,
    decode,
    encode,
    response_status,
)

_WORKER_BOOTSTRAP = (
    "import sys; sys.path[:] = [path for path in sys.path if path]; "
    "from piano_teacher.application.score_worker import main; main()"
)


class ScoreCancelled(ValueError):
    """The request lost its right to publish."""


class ScoreProcess:
    def __init__(self, cache: Path, *, executable=None, worker_args=None):
        home = os.environ.get("PIANO_TEACHER_PYTHON_HOME")
        self.executable = (executable or os.environ.get("PIANO_PYTHON")
                           or (str(Path(home) / "bin/python3") if home else sys.executable))
        self.worker_args = worker_args or ("-c", _WORKER_BOOTSTRAP)
        self.cache = cache
        self._closed = Event()
        self._active = Lock()
        self._serial = 0
        self._pid = None
        self._pidfd = None
        self._connection = None
        self._reply_binding = None

    def _start(self) -> None:
        parent, child = socket.socketpair()
        try:
            package_root = str(Path(__file__).resolve().parents[2])
            search_path = os.pathsep.join(dict.fromkeys((package_root, *filter(None, sys.path))))
            actions = [(os.POSIX_SPAWN_CLOSE, parent.fileno()),
                       (os.POSIX_SPAWN_DUP2, child.fileno(), 0)]
            if hasattr(os, "POSIX_SPAWN_CLOSEFROM"):
                actions.append((os.POSIX_SPAWN_CLOSEFROM, 3))
            elif child.fileno() > 2:
                actions.append((os.POSIX_SPAWN_CLOSE, child.fileno()))
            self._pid = os.posix_spawn(
                self.executable, (self.executable, "-S", *self.worker_args,
                                  str(os.getpid()), str(self.cache)),
                {**os.environ, "PYTHONPATH": search_path}, file_actions=actions,
                setsigdef=(signal.SIGPIPE, signal.SIGTERM), setsigmask=())
            with suppress(ProcessLookupError):
                self._pidfd = os.pidfd_open(self._pid)
            parent.settimeout(.025)
            self._connection = parent
        finally:
            child.close()
            if self._connection is None:
                parent.close()

    def _reap(self, *, interrupt: bool) -> None:
        self._reply_binding = None
        pid, self._pid = self._pid, None
        pidfd, self._pidfd = self._pidfd, None
        connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()
        try:
            if pid is None:
                return
            if interrupt:
                self._signal(pidfd, signal.SIGTERM)
            until = time.monotonic() + .05
            while time.monotonic() < until:
                if self._exited(pid):
                    return
                time.sleep(.005)
            self._signal(pidfd, signal.SIGKILL)
            with suppress(ChildProcessError):
                os.waitpid(pid, 0)
        finally:
            if pidfd is not None:
                os.close(pidfd)

    @staticmethod
    def _signal(pidfd, signum) -> None:
        # A host can auto-reap children. Signal the open process handle so
        # that a recycled numeric PID can never target an unrelated process.
        if pidfd is not None:
            with suppress(ProcessLookupError):
                signal.pidfd_send_signal(pidfd, signum)

    @staticmethod
    def _exited(pid) -> bool:
        try:
            return bool(os.waitpid(pid, os.WNOHANG)[0])
        except ChildProcessError:
            return True

    def _check_child(self) -> None:
        if self._pid is not None and self._exited(self._pid):
            self._reap(interrupt=False)

    def poll(self) -> None:
        with self._active:
            self._check_child()

    def _connect(self) -> socket.socket:
        self._check_child()
        if self._connection is None:
            self._start()
        return self._connection

    def request(self, operation, binding, make_payload, *, generation=0,
                rejected_generation=None, cancelled=None, timeout=DEADLINE_SECONDS,
                validate_json=True) -> tuple[int, bytearray]:
        if not self._active.acquire(blocking=False):
            raise RuntimeError("Score worker is busy")
        try:
            deadline = time.monotonic() + timeout

            def checkpoint():
                if self._closed.is_set() or (cancelled is not None and cancelled()):
                    raise ScoreCancelled("Score request was superseded during preparation")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Score preparation exceeded its deadline")

            checkpoint()
            if rejected_generation is not None and self._reply_binding == (binding, rejected_generation):
                self._reap(interrupt=True)
            self._serial += 1
            expected = {**binding, "version": VERSION, "id": self._serial,
                        "generation": generation, "operation": operation}
            check_request(expected)
            payload = make_payload(checkpoint)
            if not 0 < len(payload) <= REQUEST_LIMIT:
                raise ValueError("Score source exceeds the worker request limit")
            checkpoint()
            status, body = self._exchange(expected, payload, checkpoint, validate_json)
            if not status and operation == "score.bundle":
                self._reply_binding = (binding, generation)
            return status, body
        finally:
            self._active.release()

    def _exchange(self, expected, payload, checkpoint, validate_json) -> tuple[int, bytearray]:
        header = encode(expected)
        started = time.perf_counter()
        for attempt in range(2):
            try:
                checkpoint()
                channel = ScoreChannel(self._connect(), checkpoint)
                channel.send(header, METADATA_LIMIT)
                channel.send(payload, REQUEST_LIMIT)
                reply = decode(channel.receive(METADATA_LIMIT), metadata=True)
                status = response_status(reply, expected)
                body = channel.receive(REPLY_LIMIT if status == 0 else METADATA_LIMIT)
                check_payload(body, reply["sha256"], status, validate_json=validate_json)
                checkpoint()
                if os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1":
                    print("SCORE_IPC:", len(payload), len(body),
                          round((time.perf_counter() - started) * 1000, 2), "ms round trip",
                          flush=True)
                return status, body
            except (ScoreCancelled, TimeoutError):
                self._reap(interrupt=True)
                raise
            except (OSError, EOFError, ScoreProtocolError) as exc:
                self._reap(interrupt=True)
                if attempt:
                    raise RuntimeError(f"Score worker failed after restart: {exc}") from exc
        raise AssertionError("Score exchange retry loop exhausted")

    def close(self) -> None:
        self._closed.set()
        with self._active:
            self._reap(interrupt=False)

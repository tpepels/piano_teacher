"""Exec entry point for the single-threaded Verovio generation process."""

import os
import signal
import socket
import sys
import time
from contextlib import suppress
from pathlib import Path

from ..preprocessing_cache import PreprocessingCache
from ..python_worker import exit_on_parent_death
from .score_ipc import (
    BINDING_FIELDS,
    METADATA_LIMIT,
    REPLY_LIMIT,
    REQUEST_LIMIT,
    ScoreChannel,
    check_request,
    decode,
    digest,
    encode,
)
from .score_selection import decode_selection


def _stop(_signum, _frame) -> None:
    raise SystemExit(0)


def _reply(channel, cache, artifacts, previous_source):
    from .score_artifacts import ScoreArtifacts

    header = decode(channel.receive(METADATA_LIMIT), metadata=True)
    check_request(header)
    raw = channel.receive(REQUEST_LIMIT)
    started = time.perf_counter()
    binding = {key: header[key] for key in BINDING_FIELDS}
    source = (digest(raw), binding)
    try:
        if source != previous_source:
            document = decode(raw)
            selected = decode_selection(binding, document)
            artifacts = ScoreArtifacts(cache, selected, document["timing"])
            del document, selected
            previous_source = source
        del raw
        body = encode(artifacts.bundle())
        if len(body) > REPLY_LIMIT:
            raise ValueError("Score exceeds the worker response limit")
        status = 0
    except (ValueError, RuntimeError, TypeError, KeyError) as exc:
        status = 1 if isinstance(exc, ValueError) else 3
        body = encode({"error": str(exc)[:1024]})
    if os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1":
        print("SCORE_WORKER_GENERATION:", os.getpid(), header["operation"],
              round((time.perf_counter() - started) * 1000, 2), "ms",
              flush=True)
    channel.send(encode({**header, "status": status, "sha256": digest(body)}),
                 METADATA_LIMIT)
    channel.send(body, REPLY_LIMIT if status == 0 else METADATA_LIMIT)
    return artifacts, previous_source


def serve(connection: socket.socket, cache: PreprocessingCache) -> None:
    channel = ScoreChannel(connection, lambda: None)
    artifacts = previous_source = None
    try:
        while True:
            artifacts, previous_source = _reply(channel, cache, artifacts, previous_source)
    except (EOFError, BrokenPipeError):
        return


def main() -> None:
    exit_on_parent_death(int(sys.argv[1]))
    signal.signal(signal.SIGTERM, _stop)
    # Python builds predating POSIX_SPAWN_CLOSEFROM can inherit driver FDs.
    if not hasattr(os, "POSIX_SPAWN_CLOSEFROM"):
        for name in os.listdir("/proc/self/fd"):
            fd = int(name)
            if fd > 2:
                with suppress(OSError):
                    os.close(fd)
    with socket.socket(fileno=0) as connection:
        serve(connection, PreprocessingCache(Path(sys.argv[2])))


if __name__ == "__main__":
    main()

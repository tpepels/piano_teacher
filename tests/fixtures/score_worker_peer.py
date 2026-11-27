"""Controllable IPC peer for cancellation and recovery tests."""

import os
import socket
import sys
import time
from pathlib import Path

from piano_teacher.application.score_ipc import (
    METADATA_LIMIT,
    REPLY_LIMIT,
    REQUEST_LIMIT,
    ScoreChannel,
    decode,
    digest,
    encode,
)


def response(request, payload, fault, *, large):
    result = {"pid": os.getpid(), "bytes": len(payload), "id": request["id"]}
    if large:
        result["data"] = "a" * len(payload)
    body = b"{invalid}" if fault == "invalid-json" else encode(result)
    header = {**request, "status": 0, "sha256": digest(body)}
    if fault == "checksum":
        header["sha256"] = "0" * 64
    if fault == "wrong-source":
        header["fingerprint"] = "another source"
    if fault in ("wrong-id", "future-id"):
        header["id"] += 1 if fault == "future-id" else -1
    return encode(header), body


def serve(mode, work):
    with socket.socket(fileno=0) as connection:
        channel = ScoreChannel(connection, lambda: None)
        while True:
            try:
                request = decode(channel.receive(METADATA_LIMIT))
                payload = channel.receive(REQUEST_LIMIT)
            except EOFError:
                return
            first = not (work / mode).exists()
            (work / mode).write_text(str(os.getpid()))
            if first and mode == "crash":
                os._exit(33)
            if first and mode == "hang":
                time.sleep(60)
            if first and mode == "malformed":
                channel.send(b"{", METADATA_LIMIT)
                return
            header, body = response(request, payload, mode if first else "", large=mode == "large")
            channel.send(header, METADATA_LIMIT)
            channel.send(body, REPLY_LIMIT)
            if first and mode == "duplicate":
                channel.send(header, METADATA_LIMIT)
                channel.send(body, REPLY_LIMIT)


if __name__ == "__main__":
    serve(sys.argv[1], Path(sys.argv[3]))

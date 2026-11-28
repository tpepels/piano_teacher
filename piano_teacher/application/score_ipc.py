"""Bounded length-prefixed JSON over an inherited local socket."""

import hashlib
import json
import socket
import struct

VERSION = 1
OPERATIONS = frozenset(("score.bundle",))
BINDING_FIELDS = ("fingerprint", "revision", "stage_key", "hand")
METADATA_LIMIT = 8 * 1024
REQUEST_LIMIT = 32 * 1024 * 1024
REPLY_LIMIT = 64 * 1024 * 1024
DEADLINE_SECONDS = 85.0
_LENGTH = struct.Struct("!I")


class ScoreProtocolError(RuntimeError):
    """The stream cannot be reused after a framing or identity fault."""


def encode(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _metadata_fields(pairs: list[tuple[str, object]]) -> dict:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ScoreProtocolError("Duplicate score worker metadata field")
    return fields


def decode(data: bytes | bytearray, *, metadata: bool = False) -> dict:
    try:
        value = json.loads(data, object_pairs_hook=_metadata_fields if metadata else None)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ScoreProtocolError("Invalid score worker JSON") from exc
    if type(value) is not dict:
        raise ScoreProtocolError("Score worker frame must be a JSON object")
    return value


def document_bytes(value: dict, checkpoint) -> bytearray:
    """Serialize source on the asset lane in small GIL scheduling intervals."""
    parts = []
    length = 0
    output = bytearray()
    for fragment in json.JSONEncoder(separators=(",", ":"), allow_nan=False).iterencode(value):
        parts.append(fragment)
        length += len(fragment)
        if length >= 32768:
            checkpoint()
            output.extend("".join(parts).encode("utf-8"))
            if len(output) > REQUEST_LIMIT:
                raise ValueError("Score source exceeds the worker request limit")
            parts.clear()
            length = 0
    output.extend("".join(parts).encode("utf-8"))
    return output


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


class ScoreChannel:
    def __init__(self, connection: socket.socket, checkpoint):
        self.connection = connection
        self.checkpoint = checkpoint

    def _read(self, length: int) -> bytearray:
        data = bytearray(length)
        remaining = memoryview(data)
        while remaining:
            self.checkpoint()
            try:
                count = self.connection.recv_into(remaining)
            except TimeoutError:
                continue
            if not count:
                raise EOFError("Score worker closed its channel")
            remaining = remaining[count:]
        return data

    def receive(self, limit: int) -> bytearray:
        length, = _LENGTH.unpack(self._read(_LENGTH.size))
        if not 0 < length <= limit:
            raise ScoreProtocolError("Score worker frame exceeds its size limit")
        return self._read(length)

    def send(self, data: bytes | bytearray, limit: int) -> None:
        if not 0 < len(data) <= limit:
            raise ScoreProtocolError("Score worker frame exceeds its size limit")
        for part in (_LENGTH.pack(len(data)), data):
            remaining = memoryview(part)
            while remaining:
                self.checkpoint()
                try:
                    count = self.connection.send(remaining)
                except TimeoutError:
                    continue
                if not count:
                    raise EOFError("Score worker stopped accepting input")
                remaining = remaining[count:]


def check_request(header: dict) -> None:
    expected_fields = {*BINDING_FIELDS, "version", "id", "generation", "operation"}
    if (header.keys() != expected_fields
            or header.get("version") != VERSION
            or header.get("operation") not in OPERATIONS
            or header.get("hand") not in ("right", "left", "both")):
        raise ScoreProtocolError("Unsupported score worker request")
    for field in ("version", "id", "generation", "revision"):
        if type(header[field]) is not int or header[field] < 0:
            raise ScoreProtocolError("Invalid score worker request number")
    for field in ("fingerprint", "stage_key"):
        if type(header[field]) is not str or not header[field]:
            raise ScoreProtocolError("Invalid score worker source identity")


def response_status(reply: dict, expected: dict) -> int:
    bound = {key: reply.get(key) for key in expected}
    status = reply.get("status")
    checksum = reply.get("sha256")
    if (reply.keys() != {*expected, "status", "sha256"} or bound != expected
            or any(type(bound[key]) is not type(value) for key, value in expected.items())
            or type(status) is not int or status not in (0, 1, 3)
            or type(checksum) is not str or len(checksum) != 64):
        raise ScoreProtocolError("Mismatched score worker response")
    return status


def check_payload(body: bytearray, checksum: str, status: int, *, validate_json: bool) -> None:
    if digest(body) != checksum or body[:1] != b"{" or body[-1:] != b"}":
        raise ScoreProtocolError("Invalid score worker response body")
    if status:
        if type(decode(body).get("error")) is not str:
            raise ScoreProtocolError("Invalid score worker error response")
    elif validate_json:
        decode(body)

"""Regression coverage for Godot cancelling in-flight localhost requests."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from piano_teacher.transport.http import Handler


def make_handler(method: str) -> Handler:
    # Construct without opening a real socket: the goal is to exercise
    # deterministic disconnects at every HTTP response boundary.
    handler = Handler.__new__(Handler)
    handler.path = "/state" if method == "do_GET" else "/control"
    handler.engine = SimpleNamespace(
        state=lambda: {"phase": "ready"},
        control=lambda **kwargs: None,
    )
    handler.headers = {"Content-Length": "2"}
    handler.rfile = BytesIO(b"{}")
    handler._json = Mock()
    return handler


@pytest.mark.parametrize("method", ["do_GET", "do_POST"])
@pytest.mark.parametrize(
    "disconnect",
    [BrokenPipeError, ConnectionResetError, ConnectionAbortedError],
)
def test_disconnected_clients_do_not_trigger_another_reply(method, disconnect):
    handler = make_handler(method)
    handler._json.side_effect = disconnect("client went away")

    getattr(handler, method)()

    # The old implementation attempted to send a second JSON error over
    # the same dead socket and raised a second BrokenPipeError.
    assert handler._json.call_count == 1


@pytest.mark.parametrize("method", ["do_GET", "do_POST"])
def test_disconnection_while_sending_error_is_ignored(method):
    handler = make_handler(method)
    handler._json.side_effect = [
        ValueError("failed to encode response"),
        BrokenPipeError("client left while receiving error"),
    ]

    getattr(handler, method)()

    assert handler._json.call_count == 2
    assert handler._json.call_args.args[0] == 400


@pytest.mark.parametrize("method", ["do_GET", "do_POST"])
def test_connected_clients_still_receive_normal_response(method):
    handler = make_handler(method)

    getattr(handler, method)()

    handler._json.assert_called_once_with(200, {"phase": "ready"})

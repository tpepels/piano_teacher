"""Hot-plug and replacement do not allow callbacks from retired ports."""
from types import SimpleNamespace

from piano_teacher.application.midi_connection import MidiConnection
from piano_teacher.application.device_workflows import DeviceWorkflows


class FakePort:
    def __init__(self, callback):
        self.callback = callback
        self.closed = False

    def close(self):
        self.closed = True


class FakeBackend:
    def __init__(self):
        self.ports = []
        self.fail = False

    def open_input(self, name, callback):
        if self.fail:
            raise RuntimeError("unplugged")
        port = FakePort(callback)
        self.ports.append(port)
        return port


def test_device_reselection_retires_old_callback_even_same_name():
    backend = FakeBackend()
    connection = MidiConnection(backend=backend, clock=lambda: 10.0)
    received = []
    factory = lambda generation: lambda message: received.append((generation, message))
    with connection.selecting("Piano", callback=received.append, callback_factory=factory):
        pass
    first = backend.ports[-1]
    first.callback("first")
    with connection.selecting("Piano", callback=received.append, callback_factory=factory):
        pass
    second = backend.ports[-1]
    first.callback("late")
    second.callback("second")
    assert first.closed
    assert [message for _, message in received] == ["first", "second"]
    assert received[0][0] != received[1][0]


def test_restore_after_late_connection_uses_new_port_epoch():
    backend = FakeBackend()
    connection = MidiConnection(backend=backend, clock=lambda: 10.0)
    observed = []
    assert connection.restore_preferred((), "Piano", callback=observed.append) is None
    restored = connection.restore_preferred(("Piano",), "Piano", callback=observed.append)
    assert restored.connected and connection.connected
    backend.ports[-1].callback("note")
    assert observed == ["note"]


def test_selecting_connected_keyboard_is_idempotent():
    device = SimpleNamespace(device="Piano", connected=True)
    workflow = DeviceWorkflows(midi_input=device, lifecycle=None, lesson=None,
        notices=None, transport=None, library=None, clock=lambda: 10.0)
    workflow.select("Piano", callback=lambda message: None)

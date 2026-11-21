"""Test-only fake physical MIDI device for the embedded production smoke test.

Imported as Python's standard sitecustomize ONLY when its isolated test
directory is prepended to PYTHONPATH. No code under piano_teacher is patched
or modified; the single production MIDI callback receives actual mido.Message
objects from a local UDP device emulator.
"""
import os

if os.environ.get("PIANO_TEST_FAKE_MIDI_PORT"):
    import json
    import socket
    import threading

    import mido

    DEVICE = "CI Synthetic Keyboard"
    _ports = []
    _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _socket.bind(("127.0.0.1", int(os.environ["PIANO_TEST_FAKE_MIDI_PORT"])))
    _socket.settimeout(.4)
    _stopping = False

    class _TestMidiInput:
        def __init__(self, callback):
            self.callback = callback
            self.closed = False

        def close(self):
            self.closed = True

    def _names():
        return [DEVICE]

    def _open(name, *, callback, **_kwargs):
        if name != DEVICE:
            raise OSError("Synthetic MIDI test device not found")
        port = _TestMidiInput(callback)
        _ports.append(port)
        return port

    def _read():
        while not _stopping:
            try:
                packet, _ = _socket.recvfrom(1024)
            except socket.timeout:
                continue
            try:
                event = json.loads(packet)
                if event["type"] not in ("note_on", "note_off"):
                    continue
                note = int(event["pitch"])
                if note < 0 or note > 127:
                    continue
                message = mido.Message(event["type"], note=note,
                                       velocity=84 if event["type"] == "note_on" else 0)
                for port in tuple(_ports):
                    if not port.closed:
                        # Real engine on_midi callback; not a fake grader.
                        port.callback(message.copy())
            except (KeyError, TypeError, ValueError) as exc:
                print("TEST_FAKE_MIDI_BAD_PACKET:", exc, flush=True)

    mido.get_input_names = _names
    mido.open_input = _open
    threading.Thread(target=_read, daemon=True,
                     name="native-test-fake-midi-device").start()
    print("TEST_FAKE_MIDI_DEVICE_READY", DEVICE, flush=True)

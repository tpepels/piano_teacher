"""ALSA MIDI device bridge for the Qt event loop."""
from __future__ import annotations
import time
import mido
from PySide6.QtCore import QObject, Signal


class MidiInput(QObject):
    note = Signal(int, bool, float)  # pitch, key down?, monotonic timestamp

    def __init__(self) -> None:
        super().__init__()
        self.port = None

    def ports(self) -> list[str]:
        return mido.get_input_names()

    def connect(self, name: str) -> None:
        self.close()
        if name:
            self.port = mido.open_input(name, callback=self._on_message)

    def _on_message(self, message) -> None:
        if message.type == "note_on" and message.velocity > 0:
            self.note.emit(message.note, True, time.monotonic())
        elif message.type == "note_off" or (message.type == "note_on" and message.velocity == 0):
            self.note.emit(message.note, False, time.monotonic())

    def close(self) -> None:
        if self.port is not None:
            self.port.close()
            self.port = None


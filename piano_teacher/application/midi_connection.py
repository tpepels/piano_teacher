"""MIDI device lifetime, bounded discovery/reconnect and physical input facts.

The application serializes operations and cancels its take inside the release
phase. No lesson, transport, recorder or application object is retained here.
The original hardware callback is passed directly to the backend.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import time

from ..hardware_probe import HardwareProbe


@dataclass(frozen=True)
class MidiNotice:
    feedback: str
    next_action: str
    connected: bool | None = None
    sampled_at: float | None = None


@dataclass(frozen=True)
class MidiScan:
    names: tuple[str, ...] = ()
    lost: bool = False
    error: Exception | None = None

    @property
    def feedback(self) -> str:
        return (f"Cannot list MIDI input devices: {self.error}. "
                "Check your MIDI backend and connection.") if self.error is not None else ""


@dataclass
class DeviceSelection:
    """Completed selection result, published after the released port is closed."""
    notice: MidiNotice | None = None


class MidiConnection:
    SCAN_SECONDS = 3.0
    RETRY_SECONDS = 4.0

    def __init__(self, *, enabled: bool = True, backend=None):
        self.enabled = enabled
        self._backend = backend
        self.port = None
        self.device = ""
        self.next_scan_at = 0.0
        self.retry_after = 0.0
        self.input_count = 0
        self.input_note = None
        self.input_at = None
        self.probe = HardwareProbe()

    def _driver(self):
        if self._backend is not None:
            return self._backend
        import mido
        return mido

    @property
    def closed(self) -> bool:
        return self.port is not None and getattr(self.port, "closed", False)

    @property
    def connected(self) -> bool:
        return self.port is not None and not getattr(self.port, "closed", False)

    @staticmethod
    def _close(port) -> None:
        if port is not None:
            try:
                port.close()
            except Exception:
                pass  # ALSA may already have released an unplugged port.

    def _release(self, reason: str):
        port = self.port
        self.port = None
        self.device = ""
        self.input_note = None
        self.input_at = None
        self.probe.stop(reason)
        return port

    @contextmanager
    def disconnected(self, reason: str = "device_disconnected"):
        previous = self.device
        port = self._release(reason)
        try:
            yield MidiNotice(
                f"MIDI piano disconnected: {previous}. Reconnect it, then press Start.",
                "Reconnect your piano, then press Start.", connected=False)
        finally:
            self._close(port)
            self.retry_after = time.monotonic()+self.RETRY_SECONDS

    @contextmanager
    def selecting(self, name: str, *, callback):
        result = DeviceSelection()
        port = self._release("device_changed")
        try:
            yield result
        finally:
            self._close(port)
        self.retry_after = 0.0
        self.next_scan_at = time.monotonic()+self.SCAN_SECONDS
        if not isinstance(name, str):
            raise ValueError("MIDI input name must be text")
        if name:
            if not self.enabled:
                raise ValueError("MIDI input is disabled")
            try:
                self.port = self._driver().open_input(name, callback=callback)
            except Exception as exc:
                raise RuntimeError(
                    f"Cannot connect to MIDI input {name}: {exc}. Check the device and try again.") from exc
            self.device = name
            feedback = f"MIDI piano connected: {name}. Press Start when ready."
        else:
            feedback = "MIDI piano disconnected. Connect a device to enable scoring."
        result.notice = MidiNotice(feedback,
            "Press Start when you are ready." if name else "Connect your piano for feedback.",
            connected=self.port is not None)

    def scan(self) -> MidiScan:
        if not self.enabled:
            return MidiScan()
        try:
            names = tuple(self._driver().get_input_names())
        except Exception as exc:
            return MidiScan(lost=bool(self.device and not self.connected), error=exc)
        return MidiScan(names, lost=bool(self.device
            and (not self.connected or self.device not in names)))

    def scan_due(self, preferred: str) -> bool:
        now = time.monotonic()
        if self.enabled and now >= self.next_scan_at and (self.device or preferred):
            self.next_scan_at = now+self.SCAN_SECONDS
            return True
        return False

    def restore_preferred(self, names: tuple[str, ...], preferred: str, *, callback) -> MidiNotice | None:
        now = time.monotonic()
        if not (self.enabled and preferred and not self.connected
                and preferred in names and now >= self.retry_after):
            return None
        try:
            port = self._driver().open_input(preferred, callback=callback)
        except Exception as exc:
            self.retry_after = now+self.RETRY_SECONDS
            return MidiNotice(
                f"Cannot reconnect MIDI piano {preferred}: {exc}. "
                "Check the USB connection or select a device in Settings.",
                "Reconnect your piano, then press Start.")
        self.port, self.device = port, preferred
        return MidiNotice(f"MIDI piano reconnected: {preferred}. Press Start when ready.",
            "Press Start when you are ready.", connected=True, sampled_at=now)

    def observe(self, message, *, now: float) -> None:
        self.probe.receive(message, now=now)
        if message.type == "note_on" and message.velocity > 0:
            self.input_count += 1
            self.input_note = message.note
            self.input_at = now

    def diagnostics_snapshot(self) -> dict:
        return self.probe.snapshot()

    def diagnostics_action(self, action: str, *, running: bool) -> dict:
        if action == "start":
            if not self.connected:
                raise RuntimeError("Connect a MIDI piano in Settings before testing")
            if running:
                raise RuntimeError("Stop the current practice attempt before testing MIDI input")
            return self.probe.start(self.device)
        if action == "stop":
            return self.probe.stop()
        raise ValueError("Hardware diagnostics action must be start or stop")

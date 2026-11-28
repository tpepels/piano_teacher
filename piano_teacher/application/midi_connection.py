"""MIDI device lifetime, bounded discovery/reconnect and physical input facts.

The application serializes operations and cancels its take inside the release
phase. No lesson, transport, recorder or application object is retained here.
Each opened port owns its callback generation; stale ports cannot publish keys.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import re

from ..hardware_probe import HardwareProbe
from ..clock import Clock, monotonic


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

    def __init__(self, *, enabled: bool = True, backend=None, clock: Clock = monotonic):
        self._clock = clock
        self.enabled = enabled
        self._backend = backend
        self.port = None
        self.device = ""
        self.generation = 0
        self.next_scan_at = 0.0
        self.retry_after = 0.0
        self.auto_discovery = True
        self.input_count = 0
        self.input_note = None
        self.input_at = None
        self.probe = HardwareProbe(clock=clock)

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
        self.generation += 1
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
                f"Your piano was disconnected ({previous}).",
                "Switch it on or plug it in again; it is found automatically.", connected=False)
        finally:
            self._close(port)
            self.retry_after = self._clock()+self.RETRY_SECONDS

    def _open_input(self, name, callback, callback_factory=None):
        self.generation += 1
        generation = self.generation
        deliver = callback_factory(generation) if callback_factory is not None else callback
        def from_port(message):
            if generation == self.generation and self.connected:
                deliver(message)
        return self._driver().open_input(name, callback=from_port)

    @contextmanager
    def selecting(self, name: str, *, callback, callback_factory=None):
        if not isinstance(name, str):
            raise ValueError("MIDI input name must be text")
        self.auto_discovery = bool(name)
        result = DeviceSelection()
        port = self._release("device_changed")
        try:
            yield result
        finally:
            self._close(port)
        self.retry_after = 0.0
        self.next_scan_at = self._clock()+self.SCAN_SECONDS
        if name:
            if not self.enabled:
                raise ValueError("MIDI input is disabled")
            try:
                self.port = self._open_input(name, callback, callback_factory)
            except Exception as exc:
                raise RuntimeError(
                    f"Cannot connect to MIDI input {name}: {exc}. Check the device and try again.") from exc
            self.device = name
            feedback = f"Piano connected: {name}."
        else:
            feedback = "No piano selected."
        result.notice = MidiNotice(feedback,
            "Press Play when you are ready." if name else "Choose your MIDI piano in Settings.",
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
        now = self._clock()
        if self.enabled and self.auto_discovery and now >= self.next_scan_at:
            self.next_scan_at = now+self.SCAN_SECONDS
            return True
        return False

    @staticmethod
    def _candidate(names: tuple[str, ...], preferred: str) -> str | None:
        """Prefer the selected device, tolerating ALSA's changing port suffix."""
        if preferred and preferred in names:
            return preferred
        def stable(name):
            return re.sub(r"\s+\d+:\d+$", "", name).casefold()
        matches = [name for name in names if preferred and stable(name) == stable(preferred)]
        if len(matches) == 1:
            return matches[0]
        physical = [name for name in names if not any(
            marker in name.casefold() for marker in (
                "midi through", "rtmidi", "virtual midi", "system:timer", "system:announce"))]
        pianos = [name for name in physical if any(
            marker in name.casefold() for marker in ("kawai", "piano", "digital keyboard"))]
        if len(pianos) == 1:
            return pianos[0]
        return physical[0] if len(physical) == 1 else None

    def restore_preferred(self, names: tuple[str, ...], preferred: str, *, callback, callback_factory=None) -> MidiNotice | None:
        now = self._clock()
        if not (self.enabled and self.auto_discovery and not self.connected
                and now >= self.retry_after):
            return None
        name = self._candidate(names, preferred)
        if name is None:
            return None
        try:
            port = self._open_input(name, callback, callback_factory)
        except Exception as exc:
            self.retry_after = now+self.RETRY_SECONDS
            return MidiNotice(
                f"Cannot reconnect MIDI piano {name}: {exc}. "
                "Check the cable or Bluetooth, or choose the piano in Settings.",
                "Switch it on or plug it in again; it is found automatically.")
        self.port, self.device = port, name
        return MidiNotice(f"Piano connected again: {name}.",
            "Press Play when you are ready.", connected=True, sampled_at=now)

    def observe(self, message, *, now: float) -> None:
        self.probe.receive(message, now=now)
        if message.type == "note_on" and message.velocity > 0:
            self.input_count += 1
            self.input_note = message.note
            self.input_at = now

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

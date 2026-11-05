"""One authoritative hardware-key shortcut policy.

MIDI input does not report a keyboard's physical range; users teach its
endpoints once per connected device. A key belonging anywhere to the
currently selected exercise always remains a musical key. Shortcuts are
consumed before activity counters, MIDI grading, guided capture and recording.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyDecision:
    consumed: bool = False
    action: str = ""
    completed_range: tuple[int, int] | None = None


class MidiKeyShortcuts:
    def __init__(self, saved: dict | None = None):
        self.ranges = dict(saved or {})
        self.capture_device = ""
        self.capture_low: int | None = None
        self.suppressed_releases: set[int] = set()

    def configure(self, ranges: dict) -> None:
        self.ranges = dict(ranges)

    def begin_capture(self, device: str) -> None:
        if not device:
            raise ValueError("Connect a MIDI piano before setting its key range")
        self.capture_device = device
        self.capture_low = None
        self.suppressed_releases.clear()

    def cancel_capture(self) -> None:
        self.capture_device = ""
        self.capture_low = None
        self.suppressed_releases.clear()

    def status(self, device: str) -> dict:
        saved = self.ranges.get(device)
        return {
            "device": device,
            "configured": bool(saved),
            "low": saved[0] if saved else None,
            "high": saved[1] if saved else None,
            "active": bool(device and self.capture_device == device),
            "step": ("lowest" if self.capture_low is None else "highest")
            if device and self.capture_device == device else "",
            "captured_low": self.capture_low if self.capture_device == device else None,
        }

    def accept(self, message, *, device: str, exercise_pitches: frozenset[int],
               can_pause: bool, paused: bool) -> KeyDecision:
        kind = getattr(message, "type", "")
        if kind not in ("note_on", "note_off"):
            return KeyDecision()
        pitch = getattr(message, "note", -1)
        if type(pitch) is not int or not 0 <= pitch <= 127:
            return KeyDecision()
        on = kind == "note_on" and getattr(message, "velocity", 0) > 0
        if pitch in self.suppressed_releases:
            if not on:
                self.suppressed_releases.remove(pitch)
            return KeyDecision(consumed=True)
        if device and device == self.capture_device:
            if not on:
                return KeyDecision(consumed=True)
            self.suppressed_releases.add(pitch)
            if self.capture_low is None:
                self.capture_low = pitch
                return KeyDecision(consumed=True)
            if pitch <= self.capture_low:
                # Preserve the chosen lowest key and ask for a higher key.
                return KeyDecision(consumed=True)
            selected = (self.capture_low, pitch)
            self.cancel_capture()
            self.suppressed_releases.add(pitch)
            return KeyDecision(consumed=True, completed_range=selected)
        saved = self.ranges.get(device)
        if not saved or pitch in exercise_pitches:
            return KeyDecision()
        if pitch == saved[0]:
            if on:
                self.suppressed_releases.add(pitch)
                return KeyDecision(consumed=True,
                    action="resume" if paused else "pause" if can_pause else "")
            return KeyDecision(consumed=True)
        if pitch == saved[1]:
            if on:
                self.suppressed_releases.add(pitch)
                return KeyDecision(consumed=True, action="restart")
            return KeyDecision(consumed=True)
        return KeyDecision()

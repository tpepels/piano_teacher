"""One authoritative hardware-key shortcut policy.

MIDI input does not report a keyboard's physical range; users teach its
endpoints once per connected device. A key belonging anywhere to the
currently selected exercise always remains a musical key. Shortcuts are
consumed before activity counters, MIDI grading, guided capture and recording.
"""
from __future__ import annotations

from dataclasses import dataclass

RESUME_NOTE = "C"
RESUME_PITCH_CLASS = 0


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

    def discard_stale_release(self, message) -> None:
        """Release obsolete shortcut suppression without executing an action.

        A note_off captured for the previous transport can arrive after Stop
        while the worker holds the session lock. It must not become a new
        lesson command, but the corresponding held shortcut key must be free.
        """
        kind = getattr(message, "type", "")
        on = kind == "note_on" and getattr(message, "velocity", 0) > 0
        pitch = getattr(message, "note", -1)
        if kind in ("note_on", "note_off") and not on and type(pitch) is int:
            self.suppressed_releases.discard(pitch)

    def accept(self, message, *, device: str, exercise_pitches: frozenset[int],
               can_pause: bool, paused: bool, section_choice: bool = False) -> KeyDecision:
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
        if device and section_choice and not paused:
            if on and pitch % 12 in (0, 5):
                self.suppressed_releases.add(pitch)
                return KeyDecision(consumed=True,
                    action="section_repeat" if pitch % 12 == 0 else "section_next")
            return KeyDecision() # Ordinary non-choice notes remain warm-up ink.
        # While paused, a fresh C in any octave is an explicit command,
        # including when C belongs to the current exercise. The release is
        # consumed even after Resume opens the next grading window.
        if device and paused and on and pitch % 12 == RESUME_PITCH_CLASS:
            self.suppressed_releases.add(pitch)
            return KeyDecision(consumed=True, action="resume")
        saved = self.ranges.get(device)
        if not saved or pitch in exercise_pitches:
            return KeyDecision()
        if pitch == saved[0]:
            if on:
                self.suppressed_releases.add(pitch)
                return KeyDecision(consumed=True,
                    action="resume" if paused else "pause" if can_pause else "")
            return KeyDecision()
        if pitch == saved[1]:
            if on:
                self.suppressed_releases.add(pitch)
                return KeyDecision(consumed=True, action="restart")
            return KeyDecision()
        return KeyDecision()

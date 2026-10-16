"""Opt-in, bounded hardware MIDI diagnostics for a real piano session.

This observes callback timestamps; it does not infer physical key-to-computer
latency or audio output latency. No recording is kept on disk by the backend,
and none of these events enter the assessment, mastery or transport clock.
"""
from __future__ import annotations

import math
import time

MAX_EVENTS = 512
MAX_SECONDS = 90.0
CHORD_WINDOW_SECONDS = 0.080


class HardwareProbe:
    def __init__(self) -> None:
        self.active = False
        self.device = ""
        self.reason = ""
        self.started_at: float | None = None
        self.stopped_at: float | None = None
        self.events: list[dict] = []
        self.held: dict[tuple[int, int], float] = {}
        self.pedal_down: dict[int, bool] = {}
        self.note_ons = 0
        self.note_offs = 0
        self.pedal_changes = 0
        self.orphan_releases = 0
        self.repeated_attacks = 0
        self.chord_pairs = 0
        self.overflow = 0
        self.velocity_min: int | None = None
        self.velocity_max: int | None = None
        self.last_attack_at: float | None = None

    def start(self, device: str, *, now: float | None = None) -> dict:
        if not device:
            raise ValueError("Connect a MIDI piano before starting hardware diagnostics")
        instant = time.monotonic() if now is None else now
        self.__init__()
        self.active = True
        self.device = device
        self.started_at = instant
        self.reason = "recording"
        return self.snapshot(now=instant)

    def stop(self, reason: str = "completed", *, now: float | None = None) -> dict:
        instant = time.monotonic() if now is None else now
        if self.active:
            self.active = False
            self.stopped_at = instant
            self.reason = reason
        return self.snapshot(now=instant)

    def receive(self, message: object, *, now: float | None = None) -> None:
        if not self.active or self.started_at is None:
            return
        instant = time.monotonic() if now is None else now
        if instant - self.started_at >= MAX_SECONDS:
            self.stop("time_limit", now=instant)
            return
        kind = getattr(message, "type", "")
        channel = int(getattr(message, "channel", 0))
        if kind in ("note_on", "note_off"):
            pitch = int(getattr(message, "note", -1))
            velocity = int(getattr(message, "velocity", 0))
            if not (0 <= pitch <= 127 and 0 <= channel <= 15):
                return
            is_on = kind == "note_on" and velocity > 0
            key = (channel, pitch)
            if is_on:
                self.note_ons += 1
                self.velocity_min = velocity if self.velocity_min is None else min(
                    self.velocity_min, velocity)
                self.velocity_max = velocity if self.velocity_max is None else max(
                    self.velocity_max, velocity)
                if key in self.held:
                    self.repeated_attacks += 1
                if self.last_attack_at is not None and (
                        0 <= instant - self.last_attack_at <= CHORD_WINDOW_SECONDS):
                    self.chord_pairs += 1
                self.last_attack_at = instant
                self.held[key] = instant
            else:
                self.note_offs += 1
                if key not in self.held:
                    self.orphan_releases += 1
                self.held.pop(key, None)
            event = {"at_s": round(instant - self.started_at, 4),
                     "type": "note_on" if is_on else "note_off",
                     "channel": channel, "pitch": pitch}
            if is_on:
                event["velocity"] = velocity
        elif kind == "control_change" and int(getattr(message, "control", -1)) == 64:
            if not (0 <= channel <= 15):
                return
            down = int(getattr(message, "value", 0)) >= 64
            if self.pedal_down.get(channel, False) == down:
                return
            self.pedal_down[channel] = down
            self.pedal_changes += 1
            event = {"at_s": round(instant - self.started_at, 4),
                     "type": "sustain_down" if down else "sustain_up",
                     "channel": channel}
        else:
            return
        if len(self.events) < MAX_EVENTS:
            self.events.append(event)
        else:
            self.overflow += 1

    def snapshot(self, *, now: float | None = None) -> dict:
        instant = time.monotonic() if now is None else now
        if self.active and self.started_at is not None and (
                instant - self.started_at >= MAX_SECONDS):
            self.active = False
            self.stopped_at = instant
            self.reason = "time_limit"
        ending = self.stopped_at if self.stopped_at is not None else instant
        duration = max(0.0, ending - self.started_at) if self.started_at is not None else 0.0
        return {
            "active": self.active, "device": self.device, "reason": self.reason,
            "duration_s": round(duration, 3),
            "note_ons": self.note_ons, "note_offs": self.note_offs,
            "chord_pairs": self.chord_pairs,
            "velocity_min": self.velocity_min, "velocity_max": self.velocity_max,
            "pedal_changes": self.pedal_changes,
            "sustain_down": sorted(ch for ch, down in self.pedal_down.items() if down),
            "orphan_releases": self.orphan_releases,
            "repeated_attacks": self.repeated_attacks,
            "held_notes": [{"channel": channel, "pitch": pitch}
                           for channel, pitch in sorted(self.held)],
            "stored_events": len(self.events), "dropped_events": self.overflow,
            "events": list(self.events),
        }

"""Tap-along MIDI timing calibration; no sound-device latency claims.

The app plays metronome ticks from its normal timeline. The user taps a key
on each tick. Median deviation estimates an end-to-end playing offset which
includes human response and speaker output latency, not just Bluetooth input.
The result is only applied after explicit confirmation.
"""
from __future__ import annotations
from statistics import median


class MidiTapCalibration:
    bpm = 80
    ticks = 8
    period = 60.0 / bpm

    def __init__(self) -> None:
        self.active = False
        self.start_at = 0.0
        self.samples: dict[int, float] = {}
        self.result: dict | None = None

    def start(self, now: float) -> None:
        self.active = True
        self.start_at = now + 1.5
        self.samples = {}
        self.result = None

    def cancel(self) -> None:
        self.active = False

    def observe(self, at: float) -> bool:
        if not self.active:
            return False
        position = (at - self.start_at) / self.period
        index = round(position)
        delta = at - (self.start_at + index * self.period)
        if 0 <= index < self.ticks and abs(delta) <= 0.32 and index not in self.samples:
            self.samples[index] = delta
            return True
        return False

    def snapshot(self, now: float) -> dict:
        if self.active and now >= self.start_at + self.ticks * self.period:
            self.active = False
            if len(self.samples) >= 5:
                offsets = list(self.samples.values())
                middle = median(offsets)
                jitter = median(abs(value-middle) for value in offsets)
                self.result = {
                    "estimate_ms": round(middle * 1000),
                    "jitter_ms": round(jitter * 1000),
                    "samples": len(offsets),
                    "reliable": jitter <= 0.085 and abs(middle) <= 0.25,
                }
            else:
                self.result = {"samples": len(self.samples), "reliable": False,
                               "error": "At least five aligned key taps are required"}
        return {
            "active": self.active, "bpm": self.bpm,
            "beat": ((now-self.start_at)/self.period if self.active else 0.0),
            "samples": len(self.samples), "ticks": self.ticks,
            "result": self.result,
        }

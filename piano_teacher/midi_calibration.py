"""MIDI timing calibration: tap along with a click on a shared monotonic clock.

One four-click count-in, then 24 taps. Each tap is matched to the nearest
click; its delay (received - click) is what the piano, the audio path and
your own anticipation add up to. The estimate is the median of the taps
that agree with each other (clear misses are dropped), and it is accepted
when your taps are consistent (median deviation at most 60 ms). Tapping a
little ahead of the click is normal: an estimate at or below zero means no
correction is needed, not a failed calibration.
"""
from __future__ import annotations

from statistics import median
from .application.musical_scheduler import SCHEDULER


class MidiTapCalibration:
    bpm = 80
    count_in = 4
    taps = 24
    # Display grouping only (three rows of eight); never a pass/fail rule.
    ticks = 8
    rounds = taps // ticks
    period = SCHEDULER.seconds_per_beat(bpm)
    round_beats = ticks
    total_beats = count_in + taps
    # A tap belongs to the nearest click within this window (just under
    # half a beat, so slow audio paths still pair with the right click).
    match_window = .36
    min_taps = 12
    max_spread = .060      # median absolute deviation, seconds
    miss_floor = .060      # a tap this far (or 3 deviations) off is a miss
    max_correction_ms = 250

    def __init__(self) -> None:
        self.active = False
        self.start_at = 0.0
        self.delays: dict[int, float] = {}
        self.result: dict | None = None

    def start(self, now: float) -> None:
        self.active = True
        self.start_at = now + 1.0  # time to show the preparation
        self.delays = {}
        self.result = None

    def cancel(self) -> None:
        self.active = False

    def reset(self) -> None:
        self.cancel()
        self.result = None

    def observe(self, at: float) -> bool:
        if not self.active:
            return False
        index = round((at - self.start_at) / self.period)
        tap = index - self.count_in
        if not 0 <= tap < self.taps or tap in self.delays:
            return False
        delay = at - (self.start_at + index * self.period)
        if abs(delay) > self.match_window:
            return False
        self.delays[tap] = delay
        return True

    def _finish(self) -> None:
        self.active = False
        values = list(self.delays.values())
        result: dict = {"samples": len(values), "reliable": False}
        if len(values) < self.min_taps:
            result["error"] = (f"Only {len(values)} taps were heard; tap one key "
                               "with every click and try again")
            self.result = result
            return
        center = median(values)
        deviation = median(abs(v - center) for v in values)
        kept = [v for v in values
                if abs(v - center) <= max(self.miss_floor, 3 * deviation)]
        center = median(kept)
        spread = median(abs(v - center) for v in kept)
        result.update(used=len(kept), discarded=len(values) - len(kept),
                      spread_ms=round(spread * 1000))
        if len(kept) < self.min_taps:
            result["error"] = "Too many taps were far from the click; try again"
        elif spread > self.max_spread:
            result["error"] = (f"Taps varied by about {round(spread * 1000)} ms; "
                               "try again, tapping steadily with the click")
        else:
            estimate = round(center * 1000)
            result.update(reliable=True, measured_ms=estimate,
                          estimate_ms=max(0, min(self.max_correction_ms, estimate)))
            if estimate <= 0:
                result["note"] = "You tap on or ahead of the click; no correction needed"
            elif estimate > self.max_correction_ms:
                result["note"] = f"Delay is above {self.max_correction_ms} ms; using the maximum"
        self.result = result

    def advance(self, now: float) -> None:
        if self.active and ((now - self.start_at) / self.period >= self.total_beats
                            or len(self.delays) >= self.taps):
            self._finish()

    def snapshot(self, now: float) -> dict:
        beat = (now - self.start_at) / self.period
        active_beat = min(self.total_beats - 1e-8, max(0.0, beat))
        tap_beat = max(0.0, active_beat - self.count_in)
        phase = ("finished" if not self.active else "ready" if beat < 0
                 else "count_in" if beat < self.count_in else "tap")
        return {
            "active": self.active, "bpm": self.bpm,
            # Same monotonic origin as the input callback, even without score.
            "start_at_ms": self.start_at * 1000.0,
            "sampled_at_ms": now * 1000.0,
            "beat": beat, "phase": phase, "count_in": self.count_in,
            "countdown": (self.count_in - int(active_beat)
                          if phase == "count_in" else 0),
            "tap_number": (min(self.taps, 1 + int(tap_beat)) if phase == "tap" else 0),
            "taps": self.taps,
            # Every heard tap's offset from its click (ms), in order.
            "tap_offsets_ms": [round(self.delays[i] * 1000) for i in sorted(self.delays)],
            "samples": len(self.delays),
            "round": min(self.rounds, 1 + int(tap_beat // self.ticks)),
            "rounds": self.rounds, "ticks": self.ticks,
            "round_beats": self.round_beats,
            "round_samples": [sum(1 for i in self.delays if i // self.ticks == r)
                              for r in range(self.rounds)],
            "total_beats": self.total_beats,
            "progress": min(1.0, max(0.0, beat / self.total_beats)),
            "result": self.result,
        }

"""Bounded, opt-in-readable timing metrics for real local performance diagnosis.

Records end-to-end callback and /state processing times. No sampling threads,
disk writes, timers or per-frame overhead outside an O(1) deque append.
"""
from __future__ import annotations

from collections import deque
from statistics import median


class RuntimeTimings:
    def __init__(self) -> None:
        self.midi_ms: deque[float] = deque(maxlen=256)
        self.state_ms: deque[float] = deque(maxlen=128)

    @staticmethod
    def _describe(values: deque[float]) -> dict:
        if not values:
            return {"samples": 0}
        ordered = sorted(values)
        p95 = ordered[min(len(ordered)-1, (len(ordered)*95+99)//100 - 1)]
        return {
            "samples": len(ordered),
            "median_ms": round(median(ordered), 3),
            "p95_ms": round(p95, 3),
            "max_ms": round(ordered[-1], 3),
        }

    def snapshot(self) -> dict:
        return {
            "midi_callback": self._describe(self.midi_ms),
            "full_state": self._describe(self.state_ms),
            "http_server": "threaded",
            "multiprocessing": False,
            "midi_visual_delivery": "loopback UDP; HTTP state fallback",
            "measurement": "local Python processing time; excludes Bluetooth input and display latency",
        }

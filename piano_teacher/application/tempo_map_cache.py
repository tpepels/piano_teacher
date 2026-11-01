"""Cache immutable exercise tempo maps without depending on PracticeEngine.

Shaped-tempo stages may transform the whole exercise when constructing their
map. A stable stage and BPM have exactly one mapping for each attempt. The
caller retains its existing session lock; this cache creates no other clock.
"""
from __future__ import annotations


class TempoMapCache:
    def __init__(self) -> None:
        self._stage = None
        self._bpm = None
        self._map = None

    def get(self, stage, bpm: float):
        if self._stage is not stage or self._bpm != bpm:
            result = stage.tempo_map(bpm)
            self._stage = stage
            self._bpm = bpm
            self._map = result
        return self._map

    def clear(self) -> None:
        self._stage = None
        self._bpm = None
        self._map = None

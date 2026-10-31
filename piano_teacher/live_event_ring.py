"""Bounded in-memory MIDI note-on feedback for the Godot frame loop."""
from __future__ import annotations

from collections import deque


class LiveEventRing:
    def __init__(self, capacity: int = 128) -> None:
        self.events: deque[dict] = deque(maxlen=capacity)

    def publish(self, event: dict) -> None:
        self.events.append(dict(event))

    def after(self, sequence: int) -> list[dict]:
        return [dict(event) for event in self.events
                if int(event.get("sequence", 0)) > sequence]

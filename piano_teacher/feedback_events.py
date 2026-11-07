"""Acknowledged, sequenced feedback events from the practice engine to Godot.

This is the only channel that carries note feedback to the score. One log owns
one monotonically increasing sequence space for three event kinds:

``attack``      provisional physical key-down, matched to a source note
``release``     provisional physical key-up, bound to the same source note
``assessment``  authoritative per-note grade from the Python assessment

Every event names the immutable take it belongs to (piece fingerprint,
engraved score revision, transport ID, mode) and whether that take is graded.
The consumer therefore never validates an event against a possibly stale state
snapshot. Events are retained until the single consumer acknowledges them by
requesting a later sequence. A hard capacity bounds memory if the UI stops
reading; any overflow is reported in ``lost_through`` instead of being hidden.
"""
from __future__ import annotations

from collections import deque

TAKE_FIELDS = ("piece_fingerprint", "revision", "transport_id", "mode", "graded")


class FeedbackEventLog:
    def __init__(self, capacity: int = 8192) -> None:
        if capacity <= 0:
            raise ValueError("Feedback event capacity must be positive")
        self._events: deque[dict] = deque()
        self._capacity = capacity
        self.sequence = 0
        self.lost_through = 0

    def publish(self, event: dict) -> dict:
        missing = [field for field in TAKE_FIELDS if field not in event]
        if missing or event.get("kind") not in ("attack", "release", "assessment"):
            raise ValueError(f"Feedback event lacks take identity or kind: {missing}")
        self.sequence += 1
        stored = dict(event, sequence=self.sequence)
        self._events.append(stored)
        while len(self._events) > self._capacity:
            self.lost_through = self._events.popleft()["sequence"]
        return dict(stored)

    def acknowledge(self, sequence: int) -> None:
        while self._events and self._events[0]["sequence"] <= sequence:
            self._events.popleft()

    def after(self, acknowledged: int) -> dict:
        """Acknowledge ``acknowledged`` and return every later retained event."""
        self.acknowledge(acknowledged)
        return {
            "events": [dict(event) for event in self._events],
            "acknowledged": acknowledged,
            "latest": self.sequence,
            "lost_through": self.lost_through if self.lost_through > acknowledged else 0,
        }

    def pending(self) -> list[dict]:
        """Unacknowledged events, for diagnostics and tests only."""
        return [dict(event) for event in self._events]

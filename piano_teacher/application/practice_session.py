"""Single serialized application entrypoint for commands, MIDI and ticks.

The native worker and physical MIDI callback share one RLock. Every event
executes under it through the handler table built in `session_routes`;
after the outermost event commits, the accepted MIDI epoch is published
for lock-free callback sampling.
"""
from __future__ import annotations
import time

from .session_events import (
    UserCommand, ClockAdvanced, MidiShortcut, PhysicalMidi, PracticeEvent)


class PracticeSession:
    def __init__(self, *, lock, epoch, runtime_timings, clock):
        self.lock = lock
        self.epoch = epoch
        self.runtime_timings = runtime_timings
        self.clock = clock
        self._handlers = None
        self._event_depth = 0

    def bind_handlers(self, handlers) -> None:
        if self._handlers is not None:
            raise RuntimeError("Session handlers already bound")
        self._handlers = dict(handlers)

    def midi_arrival(self):
        """Lock-free immutable snapshot for the physical callback timestamp."""
        return self.epoch.committed

    def apply(self, event: PracticeEvent) -> dict | int | None:
        """Serialize the event and atomically publish its committed MIDI epoch.

        Callback identity is sampled before acquiring the lock; command,
        score adoption, cancellation and hardware input commit under it.
        """
        handler = self._handlers.get(type(event))
        if handler is None:
            raise TypeError("Unsupported practice session event")
        with self.lock:
            self._event_depth += 1
            try:
                return handler(event)
            finally:
                self._event_depth -= 1
                # MIDI shortcuts can re-enter this same RLock through a
                # second typed event. Nested events cannot publish their
                # intermediate callback epoch before the parent commits.
                if self._event_depth == 0:
                    self.epoch.commit()

    def control(self, action: str, **kwargs) -> dict:
        return self.apply(UserCommand(action, kwargs))

    def on_midi(self, message, *, received_at=None, corrected_at=None,
                deferred=False, arrival=None) -> None:
        # Direct adapters default to the most recently committed epoch;
        # physical callback adapters supply the one sampled at arrival.
        sampled = self.clock() if received_at is None else received_at
        self.apply(PhysicalMidi(message, sampled, corrected_at, deferred,
                                self.midi_arrival() if arrival is None else arrival))

    def on_shortcut(self, effect) -> None:
        self.apply(MidiShortcut(effect))

    def advance(self) -> int:
        began = time.perf_counter()
        try:
            return self.apply(ClockAdvanced())
        finally:
            self.runtime_timings.tick_ms.append(
                (time.perf_counter()-began)*1000.0)

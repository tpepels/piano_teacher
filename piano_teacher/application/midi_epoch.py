"""The accepted physical-MIDI epoch: which hardware keys may still count.

A callback samples the committed epoch before it waits for the session
lock; when its event finally executes, `admits` compares it with the
current device, source, revision, stage, hand, take and cancellation.
"""
from __future__ import annotations

from .session_events import MidiArrival
from ..grading_tolerance import match_window
from .musical_scheduler import SCHEDULER


class MidiEpoch:
    def __init__(self, *, lesson, transport, take, midi_input, corrected_time):
        self.lesson = lesson
        self.transport = transport
        self.take = take
        self.midi_input = midi_input
        self.corrected_time = corrected_time
        self.committed = self.current()

    def current(self) -> MidiArrival:
        """Current accepted epoch; caller holds the session lock."""
        plan = self.lesson.plan
        return MidiArrival(
            self.midi_input.device, self.lesson.fingerprint,
            self.lesson.revision,
            plan.identity if plan is not None else "",
            plan.hand if plan is not None else "both",
            self.transport.transport_id,
            self.take.cancellation_generation,
            bool(self.transport.auto), self.midi_input.device_generation)

    def commit(self) -> None:
        """Publish the epoch a lock-free callback will sample next."""
        self.committed = self.current()

    def same_device(self, arrival: MidiArrival) -> bool:
        return (arrival.device == self.midi_input.device and
                arrival.device_generation == self.midi_input.device_generation)

    def admits(self, arrival: MidiArrival, received_at: float | None,
               corrected_at: float | None = None) -> bool:
        current = self.current()
        # Stop, source replacement, new engraved revision, a new lesson
        # stage/hand, or explicit take cancellation invalidate queued keys.
        if (not self.same_device(arrival) or
                arrival.fingerprint != current.fingerprint or
                arrival.revision != current.revision or
                arrival.stage_key != current.stage_key or
                arrival.hand != current.hand or
                arrival.cancellation_generation != current.cancellation_generation):
            return False
        if arrival.transport_id == current.transport_id:
            return True
        # A different take epoch may accept a late-arriving hardware key
        # only during a same-source automatic repeat, after the new
        # physical start. Manual restart/Stop never inherits old keys.
        if (not arrival.automatic or not current.automatic or
                not self.transport.running or self.transport.paused):
            return False
        if received_at is None:
            # An unspecified hardware timestamp can never authorize a
            # previous take's queued key in a newer transport epoch.
            return False
        plan = self.lesson.plan
        if plan is None:
            return False
        # The same-source rollover may accept a legitimate slightly early
        # first attack. Ingress still checks the exact measure window.
        return (self.corrected_time(received_at, corrected_at)
                >= self.transport.run_at-match_window(SCHEDULER.seconds_per_beat(plan.bpm)))

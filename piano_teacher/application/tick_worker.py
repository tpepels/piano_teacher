"""One worker tick: bounded transitions, deferred MIDI, one publication.

Runs inside PracticeSession's lock. Transition decisions belong to
PracticeTimeline; this class only bounds the same-tick handoff loop,
replays MIDI deferred during the handoff under the epoch gate, and
chooses the next tick interval.
"""
from __future__ import annotations

MAX_SAME_TICK_TRANSITIONS = 17


class TickWorker:
    def __init__(self, *, timeline, publisher, transport, take, lesson,
                 midi_input, epoch, deliver, notices, clock):
        self.timeline = timeline
        self.publisher = publisher
        self.transport = transport
        self.take = take
        self.lesson = lesson
        self.midi_input = midi_input
        self.epoch = epoch
        self.deliver = deliver
        self.notices = notices
        self.clock = clock

    def advance(self) -> int:
        transitions = 0
        try:
            # Same native transaction: settle musical handoffs, replay MIDI
            # using the new take identity, then publish a single final state.
            while True:
                if transitions >= MAX_SAME_TICK_TRANSITIONS:
                    raise RuntimeError(
                        "Practice transitions exceeded the bounded same-tick handoff")
                transitions += 1
                if not self.timeline.update_transition():
                    break
        except Exception:
            self.transport.freeze_after_fault(self.clock())
            # A failing transition bypasses the normal publish_settled()
            # tail. Reconcile the original physical take's current paused
            # status without reentering assessment or successor effects.
            self.publisher.publish_failed_transition()
            self.notices.fault("Could not save or finish the practice transition",
                "Check storage or the reported error, then Resume to retry this same take.")
            raise
        while self.midi_input.deferred_midi:
            item = self.midi_input.deferred_midi.popleft()
            # The original ingress key is part of the immutable queued note.
            # Use the same epoch gate as an in-flight physical callback.
            if not self.epoch.admits(
                    item.arrival, item.received_at, item.corrected_at):
                continue
            self.deliver(item.message, received_at=item.received_at,
                         corrected_at=item.corrected_at, deferred=True)
        self.publisher.publish_settled()
        return self.interval_ms()

    def interval_ms(self) -> int:
        if self.lesson.plan is None or self.transport.paused:
            return 250
        if (self.transport.running
                or self.transport.preparation_pending
                or self.take.pending_result is not None
                or self.transport.pending_rewind is not None
                or self.transport.mode == "listen"):
            return 20
        return 100

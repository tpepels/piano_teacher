"""Single monotonic native-worker entry and bounded next-wakeup decision.

The native queue is the only command/tick worker. This use case executes
the existing PracticeTimeline and delayed MIDI ingress under the single
application lock; it does not start a thread or own another clock.
"""
from __future__ import annotations
import time


class ApplicationWorker:
    def __init__(self, *, lock, timeline, midi_ingress, midi_application_input,
                 source_identity, visual_transport, playback_session,
                 attempt_settlement, runtime_timings):
        self.lock = lock
        self.timeline = timeline
        self.midi_ingress = midi_ingress
        self.midi_application_input = midi_application_input
        self.source_identity = source_identity
        self.visual_transport = visual_transport
        self.playback_session = playback_session
        self.attempt_settlement = attempt_settlement
        self.runtime_timings = runtime_timings

    def advance(self) -> int:
        began = time.perf_counter()
        try:
            with self.lock:
                # The native tick is one ordered session transaction:
                # settle all musical handoffs, replay timestamp-preserving
                # boundary input against the resulting take, then publish.
                # No interim state projection may outrun deferred MIDI.
                self.timeline.settle_transitions()
                while self.midi_ingress.deferred:
                    message, received_at, corrected_at, _transport = self.midi_ingress.deferred.popleft()
                    self.midi_application_input.receive_message(
                        message, received_at=received_at,
                        corrected_at=corrected_at, deferred=True)
                self.timeline.publish_settled()
                if self.source_identity.plan is None or self.visual_transport.paused:
                    return 250
                if (self.playback_session.running
                        or self.visual_transport.preview_loop_pending
                        or self.visual_transport.preparation_pending
                        or self.attempt_settlement.pending_result is not None
                        or self.visual_transport.pending_rewind is not None
                        or self.playback_session.mode == "listen"):
                    return 20
                return 100
        finally:
            self.runtime_timings.tick_ms.append(
                (time.perf_counter() - began) * 1000.0)

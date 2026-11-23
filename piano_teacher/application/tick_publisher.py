"""Publish one settled tick: transport ledger, score presentation, live marks."""
from __future__ import annotations
import logging


class TickPublisher:
    def __init__(self, *, transport, transport_timing, read_models,
                 live_feedback_workflows):
        self.transport = transport
        self.transport_timing = transport_timing
        self.read_models = read_models
        self.live_feedback_workflows = live_feedback_workflows

    def publish_failed_transition(self) -> None:
        """Make a faulted tick visibly paused without replaying any effects.

        The failed event can have already stopped grading or installed an
        idempotent recovery effect. Never rerun it merely to bring the
        physical authorization ledger into agreement with the paused clock.
        """
        self.transport.advance(self.transport_timing.playback_facts())

    def publish_settled(self) -> None:
        """Publish one accepted outcome after transitions and deferred MIDI.

        Replaying deferred hardware events before this publication makes
        controls, live feedback and transport describe the same final source.
        """
        self.transport.advance(self.transport_timing.playback_facts())
        self.read_models.prepare_score_presentation()
        try:
            self.live_feedback_workflows.publish_live()
        except Exception:
            logging.getLogger(__name__).exception(
                "Live assessment publication failed; skipping this tick")


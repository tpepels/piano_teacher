"""The two ways a Listen example ends: its audio finished, or it failed.

Owned in one place so every caller (commands, tick, timed playback,
source changes) applies the same transport and notice effects.
"""
from __future__ import annotations


class ListenOutcomes:
    def __init__(self, *, listen, transport, notices):
        self.listen = listen
        self.transport = transport
        self.notices = notices

    def finish(self, now: float) -> bool:
        """End a running Listen example whose audio has finished."""
        if not (self.transport.running
                and self.listen.finished(now=now, run_at=self.transport.run_at)):
            return False
        self.transport.finish_take()
        self.notices.feedback = "Example complete"
        self.notices.next_action = (
            "Choose Learn to find the notes, or Practice to play the rhythm.")
        return True

    def apply_failure(self) -> None:
        """Surface a failed Listen audio preparation and wait for the player."""
        failure = self.listen.take_failure()
        if failure is not None:
            self.transport.wait_for_player()
            self.notices.publish(failure, failure)

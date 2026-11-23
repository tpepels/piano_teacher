"""Owner of learner-facing status and next-action text.

Read models sample these values; messages do not select a lesson, authorize
playback or change the authoritative grading timeline.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class SessionNotices:
    feedback: str = "Open a MIDI file"
    next_action: str = "Open a MIDI file."
    _fault_action: str = ""

    def publish(self, feedback: str, next_action: str) -> None:
        self.feedback = feedback
        self.next_action = next_action

    def fault(self, feedback: str, next_action: str) -> None:
        """A recoverable failure; its instruction lasts until recovery."""
        self.publish(feedback, next_action)
        self._fault_action = next_action

    def clear_fault(self) -> None:
        """Drop a fault instruction once recovered, unless already replaced."""
        if self._fault_action and self.next_action == self._fault_action:
            self.next_action = ""
        self._fault_action = ""

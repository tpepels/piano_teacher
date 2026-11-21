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

    def publish(self, feedback: str, next_action: str) -> None:
        self.feedback = feedback
        self.next_action = next_action

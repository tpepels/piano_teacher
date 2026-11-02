"""Pure command classification for the single locked PracticeEngine entry point.

Command effects are implemented by domain methods on PracticeEngine or its
existing collaborators. This router receives no engine, callbacks or services.
Unknown actions go to the source-stage validator, preserving the public error.
"""
from __future__ import annotations

from typing import Literal

ControlRoute = Literal[
    "calibration", "reset", "acknowledgement", "listening",
    "learning", "transport", "stage"
]


class ControlDispatcher:
    CALIBRATION = frozenset((
        "calibration_start", "calibration_cancel",
        "calibration_apply", "calibration_reset"))
    ACKNOWLEDGEMENT = frozenset(("score_ready", "demo_ready"))
    LISTENING = frozenset((
        "listen", "perform", "practice_weak", "review_retry", "seek"))
    LEARNING = frozenset((
        "learn_next", "skip_stage", "place_original", "revisit_trouble",
        "learn", "learn_retry", "open_at", "hints"))
    TRANSPORT = frozenset((
        "practice", "stop", "start", "restart", "pause", "resume"))

    @classmethod
    def route(cls, action: str) -> ControlRoute:
        if action in cls.CALIBRATION:
            return "calibration"
        if action == "reset_path":
            return "reset"
        if action in cls.ACKNOWLEDGEMENT:
            return "acknowledgement"
        if action in cls.LISTENING:
            return "listening"
        if action in cls.LEARNING:
            return "learning"
        if action in cls.TRANSPORT:
            return "transport"
        return "stage"

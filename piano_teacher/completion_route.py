"""Pure completion routing for post-performance practice decisions.

A partial recovery never grants mastery. Explicit performance and section
review routes take precedence over full-passage practice; preview never grades.
No transport clocks, persistence, renderers or live engine state are accessed.
"""
from __future__ import annotations

from typing import Literal

CompletionRoute = Literal["perform", "section_review", "partial_recovery", "full_passage"]


def completion_route(mode: str, review_end_beat: float | None,
                     play_from_beat: float) -> CompletionRoute:
    if mode == "perform":
        return "perform"
    if review_end_beat is not None:
        return "section_review"
    if play_from_beat > 1e-6:
        return "partial_recovery"
    return "full_passage"

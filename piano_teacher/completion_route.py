"""Pure completion routing for post-performance practice decisions.

A completed take of the final test (perform) is reviewed; every other
take is a full passage of the selected window. No transport clocks,
persistence, renderers or live engine state are accessed.
"""
from __future__ import annotations

from typing import Literal
from dataclasses import dataclass

CompletionRoute = Literal["perform", "full_passage"]


def completion_route(mode: str) -> CompletionRoute:
    return "perform" if mode == "perform" else "full_passage"


@dataclass(frozen=True, slots=True)
class CompletionEffect:
    action: str
    exposure: object = None


def completion_effect(route: CompletionRoute, decision) -> CompletionEffect:
    """Dispatch one selected teaching consequence; never select another."""
    return CompletionEffect(route)

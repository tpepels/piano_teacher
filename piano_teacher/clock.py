"""The application's one seam for monotonic time.

Every time-dependent component receives a ``Clock`` from its owner instead of
reading ``time.monotonic()`` itself. The engine passes its own clock to its
collaborators, so a test (or a replay) can drive the whole session with one
injected function. ``monotonic`` reads the system clock at call time.
"""
from __future__ import annotations

import time
from typing import Callable

Clock = Callable[[], float]


def monotonic() -> float:
    return time.monotonic()

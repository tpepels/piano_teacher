"""Cross-attempt trouble history for one active course stage.

A stopped take clears only its own recorder and assessment output. The
consecutive failure key/count survive successive retries until the course
explicitly changes stage or clears the observed difficult window.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(slots=True)
class RecoveryStreak:
    key: tuple | None = None
    count: int = 0

    def record(self, key: tuple | None, count: int) -> None:
        self.key = key
        self.count = count

    def clear(self) -> None:
        self.key = None
        self.count = 0

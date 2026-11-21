"""Installed MIDI source identity and published asset generation.

The learning plan owns curriculum state. This object holds the currently
installed immutable source identifier and the revision of its drawn assets.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(slots=True)
class SourceIdentity:
    source: str | None = None
    fingerprint: str = ""
    warmup: bool = False
    revision: int = 0

    def install(self, *, source: str, fingerprint: str, warmup: bool) -> None:
        self.source = source
        self.fingerprint = fingerprint
        self.warmup = warmup

    def advance_revision(self) -> None:
        self.revision += 1

    def publish_revision(self, revision: int) -> None:
        self.revision = revision

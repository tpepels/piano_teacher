"""Serializable case identity shared by the public CLI and spawned workers."""
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditCase:
    name: str
    filename: str
    first_bar: int
    last_bar: int
    hand: str = "both"
    max_density: float = 640.0
    max_tiny_rests: int = 8
    max_dots: int = 2
    features: tuple[str, ...] = ()
    min_lookahead_beats: float = 0.0


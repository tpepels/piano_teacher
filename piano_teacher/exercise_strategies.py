"""The selectable exercise strategy and the fixed built-in warm-up route.

The desktop app offers one exercise strategy: adaptive Coda + Fukuda
(``coda-fukuda-midi``, owner decision 2026-11-11). Its lesson generator
lives in lesson_generators; a strategy here is only the registered name.

``source-progression`` is not selectable. It is the fixed route of the
built-in warm-ups and the source-preserving baseline that LearningPlan
uses when no strategy is named (non-MIDI fixtures, tools).
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_STRATEGY = "coda-fukuda-midi"
WARMUP_STRATEGY = "source-progression"

# The only entry the settings picker offers.
APP_STRATEGIES = (
    (DEFAULT_STRATEGY, "Coda + Fukuda · MIDI combined lessons"),
)


@dataclass(frozen=True)
class ExerciseStrategy:
    """A registered whole-piece lesson generator, selected by name."""
    name: str


def available_strategies() -> tuple[dict[str, str | bool], ...]:
    """Expose the selectable strategy and its capabilities as metadata."""
    from .lesson_generators import lesson_generator_registration
    result = []
    for key, label in APP_STRATEGIES:
        registration = lesson_generator_registration(key)
        result.append({
            "id": key, "label": label,
            "midi_only": bool(registration and registration.midi_only),
        })
    return tuple(result)


def resolve_strategy(spec: str | None, *, piece=None) -> ExerciseStrategy:
    if spec is None:
        spec = WARMUP_STRATEGY
    if not isinstance(spec, str):
        raise TypeError("An exercise strategy is selected by its registered name")
    from .lesson_generators import lesson_generator_registration
    registration = lesson_generator_registration(spec)
    if registration is None:
        raise ValueError(f"Unknown exercise strategy {spec!r}")
    if registration.midi_only and (piece is None or
            piece.source_format != "midi" or piece.source_musicxml):
        raise ValueError(f"{spec} lesson generation requires an imported MIDI piece")
    return ExerciseStrategy(spec)

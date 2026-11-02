"""Published Coda exercise-catalog request schema, NOT a lesson curriculum.

Source: annieetang/coda_backend@a4eb85dfc2bd418818ca9ff775c0a11ccccb3530
music/exercise.py:get_all_exercises + ExerciseLine.generate_exercises
api/endpoints.py:generate_exercises.

The original HTTP API receives explicit start/end measures and returns
categorized, *unordered* exercise alternatives. It never computes a
whole-piece lesson sequence. This module carries the exact category and
parameter enumeration into our MIDI adapter. Generated MIDI engraving
and the application's selected practice order remain independent policies.
"""
from __future__ import annotations

from dataclasses import dataclass

from .coda_auto_chord_levels import original_chord_levels

AUTHOR_REVISION = "a4eb85dfc2bd418818ca9ff775c0a11ccccb3530"
AUTHOR_CATEGORIES = (
    "Score Level",
    "Part Level",
    "Voice Level: Original",
    "Voice Level: Dotted",
    "Voice Level: Chordified",
    "Voice Level: Slowed Down",
)
# Both patterns and both factors appear directly in ExerciseLine.generate_exercises.
AUTHOR_DOTTED_PATTERNS = ((1.5, 0.5), (0.5, 1.5))
AUTHOR_SLOWDOWN_FACTORS = (2, 4)


@dataclass(frozen=True)
class CodaCatalogRequest:
    category: str
    variant: str
    parameter: int | tuple[float, float] | None = None


def catalog_requests(quantization: int, numerator: int,
                     denominator: int) -> tuple[CodaCatalogRequest, ...]:
    """Enumerate one source voice's complete original Coda request set.

    Original author may return None or invalid output for a request. A
    requested category is not proof of a successfully generated exercise.
    Width zero is deliberately retained to expose an original bug.
    """
    return (
        CodaCatalogRequest("Voice Level: Original", "original"),
        *(CodaCatalogRequest("Voice Level: Dotted",
                             "dotted-"+("long-short" if i==0 else "short-long"),
                             pattern)
          for i,pattern in enumerate(AUTHOR_DOTTED_PATTERNS)),
        *(CodaCatalogRequest("Voice Level: Chordified",f"chord-{width}",width)
          for width in original_chord_levels(
              quantization,numerator,denominator)),
        *(CodaCatalogRequest("Voice Level: Slowed Down",f"slow-x{factor}",factor)
          for factor in AUTHOR_SLOWDOWN_FACTORS),
    )


def score_excerpt_categories() -> tuple[str, ...]:
    """The /generate endpoint supports one caller-selected score excerpt."""
    return AUTHOR_CATEGORIES

"""Pure source-bar to course-section selection; no transport/UI state."""
from __future__ import annotations

from dataclasses import dataclass

from .measure_grid import bar_number_at


def locate_course_section(plan, bar: int):
    """Return (exercise index, section, playable source bar).

    The caller validates the requested bar and owns all state transitions.
    A silent requested bar opens at the next actual attack, not an empty
    teaching fragment. Original source boundaries remain authoritative.
    """
    # A requested measure can be silent even inside a consolidated
    # course section. Start at the next source measure with a real
    # attack, rather than opening an empty teaching fragment.
    next_attacks = [note.start for note in plan.piece.notes
                    if note.start >= plan.piece.bar_boundaries[bar-1]-1e-7]
    if not next_attacks:
        raise ValueError("No playable notes at or after that measure")
    playable_bar = bar_number_at(plan.piece.bar_boundaries,
                                 min(next_attacks), 1)
    bar = max(bar, playable_bar)
    # Find the smallest course 'learn' section containing that
    # measure; the original source grid controls all positions.
    candidates = [(i, ex) for i, ex in enumerate(plan.exercises)
                  if ex.kind == "learn" and ex.phrase.first_bar <= bar <= ex.phrase.last_bar]
    if not candidates:
        candidates = [(i, ex) for i, ex in enumerate(plan.exercises)
                      if ex.kind == "learn" and ex.phrase.first_bar > bar]
    if not candidates:
        raise ValueError("No playable notes at or after that measure")
    index, section = min(candidates, key=lambda item:
        (item[1].phrase.first_bar if item[1].phrase.first_bar > bar else bar,
         item[1].phrase.last_bar-item[1].phrase.first_bar))
    return index, section, max(bar, section.phrase.first_bar)


@dataclass(frozen=True)
class SourceOpening:
    """Validated source measure target; transport still belongs to the engine."""
    exercise_index: int
    bar: int
    mode: str


def choose_source_opening(plan, *, bar, mode, warmup: bool) -> SourceOpening:
    if plan is None:
        raise ValueError("Open a piece first")
    if warmup:
        raise ValueError("Warm-ups use their own hand progression")
    last_bar = len(plan.piece.bar_boundaries) - 1
    if type(bar) is not int or not 1 <= bar <= last_bar:
        raise ValueError(f"Choose a whole measure between 1 and {last_bar}")
    if mode not in ("learn", "practice"):
        raise ValueError("Choose Learn Notes or Practice Rhythm")
    index, _section, selected_bar = locate_course_section(plan, bar)
    return SourceOpening(index, selected_bar, mode)

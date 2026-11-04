"""Configurable mistake-response policies for MIDI practice.

Pure source-beat decisions. Detection, assessment, scheduling, persistence,
engraving and score revisions stay with their current owners. Each policy
receives immutable evidence and returns an action; adding a response needs
only a new registered Policy, never another engine branch.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class MistakePolicy:
    name: str
    label: str
    description: str
    interrupt_rolling: bool
    rolling_tempo_factor: float
    whole_tempo_factor: float
    focus_measures: int
    guided_after: int | None
    whole_focus: bool = False

    def __post_init__(self):
        if (not 0 < self.rolling_tempo_factor <= 1 or
                not 0 < self.whole_tempo_factor <= 1 or
                self.focus_measures < 1 or
                (self.guided_after is not None and self.guided_after < 1)):
            raise ValueError("Invalid mistake-response policy")


@dataclass(frozen=True)
class RollingResponse:
    restart_beat: float
    end_beat: float
    bpm: int
    guided: bool
    count: int
    trouble_key: tuple
    mode: str


@dataclass(frozen=True)
class WholeResponse:
    bpm: int
    restart_beat: float
    mode: str


_POLICIES = {
    policy.name: policy for policy in (
        MistakePolicy("adaptive", "Adaptive recovery",
                      "Two-measure rewind, 10% slowdown, guided help after repeated errors.",
                      True, .9, 1.0, 2, 2),
        MistakePolicy("steady-repeat", "Repeat at current tempo",
                      "Repeat the difficult passage without changing its tempo or showing guided prompts.",
                      True, 1.0, 1.0, 2, None),
        MistakePolicy("slow-practice", "Slower, accurate repetition",
                      "Reduce the tempo more aggressively and rebuild accuracy before speeding up.",
                      True, .8, .9, 2, None),
        MistakePolicy("micro-loop", "Isolate difficult measures",
                      "Rewind to the most recent difficult measure; use a focused partial take.",
                      True, .9, .9, 1, 3, True),
        MistakePolicy("guided-repair", "Guided repair",
                      "After mistakes, identify the notes without timing pressure before retrying.",
                      True, .9, 1.0, 2, 1),
        MistakePolicy("finish-then-review", "Finish the phrase",
                      "Ignore mid-phrase interruptions; grade at the end and retry then.",
                      False, 1.0, 1.0, 2, None),
    )
}


def available_mistake_policies() -> list[dict[str, str]]:
    return [{"id": p.name, "label": p.label, "description": p.description}
            for p in _POLICIES.values()]


def resolve_mistake_policy(name: str) -> MistakePolicy:
    if type(name) is not str or name not in _POLICIES:
        raise ValueError("Unknown mistake-response policy")
    return _POLICIES[name]


def _scaled_bpm(bpm: int, minimum_bpm: int, factor: float) -> int:
    return max(minimum_bpm, round(bpm * factor))


def _bar_start(grid: Sequence[float], beat: float) -> float:
    if len(grid) < 2 or not grid[0] <= beat <= grid[-1]:
        raise ValueError("Recovery beat is outside the source meter grid")
    return grid[max(0, min(len(grid) - 2, bisect_right(grid, beat + 1e-8) - 1))]


def rolling_response(
    policy: MistakePolicy, decision, *, identity: str, bpm: int,
    minimum_bpm: int, previous_key: tuple | None, previous_count: int,
    grid: Sequence[float], allow_guided: bool = True,
) -> RollingResponse:
    """Return a metrical rewind; preserve source identity and learner history."""
    if decision.end_beat not in grid:
        raise ValueError("The recovery boundary must end on a source bar")
    index = grid.index(decision.end_beat)
    start = max(decision.restart_beat, grid[max(0, index - policy.focus_measures)])
    key = identity, start, decision.end_beat
    count = previous_count + 1 if key == previous_key else 1
    guided = (allow_guided and policy.guided_after is not None and
              count >= policy.guided_after)
    return RollingResponse(
        restart_beat=start, end_beat=decision.end_beat,
        bpm=_scaled_bpm(bpm, minimum_bpm, policy.rolling_tempo_factor),
        guided=guided, count=count, trouble_key=key, mode=policy.name)


def whole_response(
    policy: MistakePolicy, result, *, phrase, grid: Sequence[float],
    bpm: int, minimum_bpm: int, play_from_beat: float,
) -> WholeResponse:
    """Full-take recovery uses graded source attacks, not inferred timing."""
    start = play_from_beat
    if policy.whole_focus:
        # Only a real graded incorrect attack may designate the difficult bar.
        # For sparse/ungraded results, safely retry from the current opening.
        incorrect = sorted(
            (n.note.start - phrase.start for n in getattr(result, "notes", ())
             if n.status in ("wrong", "missed") and
             phrase.start + play_from_beat <= n.note.start < phrase.end),
            reverse=True)
        if incorrect:
            start = max(play_from_beat, _bar_start(grid, incorrect[0]))
    return WholeResponse(
        bpm=_scaled_bpm(bpm, minimum_bpm, policy.whole_tempo_factor),
        restart_beat=start, mode=policy.name)

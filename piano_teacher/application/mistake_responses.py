"""Configurable mistake-response policies for MIDI practice.

Pure source-beat decisions. Detection, assessment, scheduling, persistence,
engraving and score revisions stay with their current owners. Each policy
receives immutable evidence and returns an action; adding a response needs
only a new registered Policy, never another engine branch.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Callable, Sequence


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
    # Independent algorithms receive only immutable explicit facts.
    # The core never imports their implementations or branches on their IDs.
    rolling_handler: Callable[[RollingEvidence], RollingResponse] | None = field(
        default=None, repr=False, compare=False)
    whole_handler: Callable[[WholeEvidence], WholeResponse] | None = field(
        default=None, repr=False, compare=False)

    def __post_init__(self):
        if (not self.name or not self.label.strip() or not self.description.strip() or
                not 0 < self.rolling_tempo_factor <= 1 or
                not 0 < self.whole_tempo_factor <= 1 or
                self.focus_measures < 1 or
                (self.guided_after is not None and self.guided_after < 1)):
            raise ValueError("Invalid mistake-response policy")


@dataclass(frozen=True)
class RollingEvidence:
    decision: object
    identity: str
    bpm: int
    minimum_bpm: int
    previous_key: tuple | None
    previous_count: int
    grid: tuple[float, ...]
    allow_guided: bool


@dataclass(frozen=True)
class WholeEvidence:
    result: object
    phrase: object
    grid: tuple[float, ...]
    bpm: int
    minimum_bpm: int
    play_from_beat: float


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


def register_mistake_policy(policy: MistakePolicy) -> None:
    """Register one source-bound recovery algorithm at application startup."""
    if not isinstance(policy, MistakePolicy) or policy.name in _POLICIES:
        raise ValueError("Duplicate or invalid mistake-response registration")
    _POLICIES[policy.name] = policy


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
    facts = RollingEvidence(
        decision, identity, bpm, minimum_bpm, previous_key, previous_count,
        tuple(grid), allow_guided)
    if decision.end_beat not in facts.grid:
        raise ValueError("The recovery boundary must end on a source bar")
    if policy.rolling_handler is not None:
        chosen = policy.rolling_handler(facts)
    else:
        index = facts.grid.index(decision.end_beat)
        start = max(decision.restart_beat,
                    facts.grid[max(0, index - policy.focus_measures)])
        key = identity, start, decision.end_beat
        count = previous_count + 1 if key == previous_key else 1
        guided = (allow_guided and policy.guided_after is not None and
                  count >= policy.guided_after)
        chosen = RollingResponse(
            restart_beat=start, end_beat=decision.end_beat,
            bpm=_scaled_bpm(bpm, minimum_bpm, policy.rolling_tempo_factor),
            guided=guided, count=count, trouble_key=key, mode=policy.name)
    if (not isinstance(chosen, RollingResponse) or
            chosen.mode != policy.name or
            chosen.end_beat != decision.end_beat or
            chosen.restart_beat not in facts.grid or
            chosen.restart_beat < decision.restart_beat or
            chosen.restart_beat >= decision.end_beat or
            not minimum_bpm <= chosen.bpm <= bpm or
            chosen.count < 1 or
            chosen.trouble_key != (identity, chosen.restart_beat, chosen.end_beat) or
            (chosen.guided and not allow_guided)):
        raise ValueError("Invalid source-bound rolling response")
    return chosen


def whole_response(
    policy: MistakePolicy, result, *, phrase, grid: Sequence[float],
    bpm: int, minimum_bpm: int, play_from_beat: float,
) -> WholeResponse:
    """Full-take recovery uses graded source attacks, not inferred timing."""
    facts = WholeEvidence(result, phrase, tuple(grid), bpm,
                          minimum_bpm, play_from_beat)
    if policy.whole_handler is not None:
        chosen = policy.whole_handler(facts)
    else:
        start = play_from_beat
        if policy.whole_focus:
            # Only an actual incorrect note can select a source measure.
            incorrect = sorted(
                (n.note.start - phrase.start for n in getattr(result, "notes", ())
                 if n.status in ("wrong", "missed") and
                 phrase.start + play_from_beat <= n.note.start < phrase.end),
                reverse=True)
            if incorrect:
                start = max(play_from_beat, _bar_start(grid, incorrect[0]))
        chosen = WholeResponse(
            bpm=_scaled_bpm(bpm, minimum_bpm, policy.whole_tempo_factor),
            restart_beat=start, mode=policy.name)
    if (not isinstance(chosen, WholeResponse) or
            chosen.mode != policy.name or
            not minimum_bpm <= chosen.bpm <= bpm or
            chosen.restart_beat < play_from_beat or
            chosen.restart_beat >= phrase.end - phrase.start or
            (chosen.restart_beat != play_from_beat and
             chosen.restart_beat not in facts.grid)):
        raise ValueError("Invalid source-bound whole-take response")
    return chosen

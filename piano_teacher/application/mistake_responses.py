"""Configurable mistake-response policies for MIDI practice.

Pure source-beat decisions. Detection, assessment, scheduling, persistence,
engraving and score revisions stay with their current owners. Each policy
receives immutable evidence and returns an action; adding a response needs
only a new registered Policy, never another engine branch.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
import hashlib
from math import isfinite
from typing import Callable, Sequence

from ..lesson_settings import SETTINGS


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
    version: str = "registered-recovery-v1"

    def __post_init__(self):
        if (not self.name or not self.label.strip() or not self.description.strip() or
                not 0 < self.rolling_tempo_factor <= 1 or
                not 0 < self.whole_tempo_factor <= 1 or
                self.focus_measures < 1 or
                (self.guided_after is not None and self.guided_after < 1)):
            raise ValueError("Invalid mistake-response policy")


@dataclass(frozen=True)
class AdaptiveAttempt:
    """One explicit source/stage/hand/rules-scoped exposure; no learner inference."""
    identity: str
    start_beat: float
    end_beat: float
    bpm: int
    wrong_beats: tuple[float, ...]
    missed_beats: tuple[float, ...]
    timing_errors: int | None
    hold_errors: int | None
    accepted: bool | None
    assisted: bool = False
    action: str = "repeat"
    extra_errors: int = 0
    reliable: bool = True

    def __post_init__(self):
        object.__setattr__(self, "wrong_beats", tuple(self.wrong_beats))
        object.__setattr__(self, "missed_beats", tuple(self.missed_beats))
        if (type(self.identity) is not str or not self.identity
                or not all(isfinite(v) for v in (self.start_beat, self.end_beat))
                or not 0 <= self.start_beat < self.end_beat or type(self.bpm) is not int or self.bpm < 1
                or type(self.assisted) is not bool or type(self.reliable) is not bool
                or type(self.extra_errors) is not int or type(self.action) is not str
                or any(not isfinite(v) or not self.start_beat <= v < self.end_beat
                       for v in self.wrong_beats + self.missed_beats)
                or any(value is not None and (type(value) is not int or value < 0)
                       for value in (self.timing_errors, self.hold_errors, self.extra_errors))
                or self.accepted is not None and type(self.accepted) is not bool
                or self.accepted is True and (self.wrong_beats or self.missed_beats or self.extra_errors)):
            raise ValueError("Invalid source-bound adaptive attempt")


@dataclass(frozen=True)
class AdaptiveContext:
    identity: str
    attempts: tuple[AdaptiveAttempt, ...]
    episode_action_count: int = 0
    original_start_beat: float = 0.0
    original_end_beat: float | None = None
    source_attacks: int | None = None
    attacks_per_beat: float | None = None
    reference_bpm: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "attempts", tuple(self.attempts))
        if (type(self.identity) is not str or not self.identity
                or type(self.episode_action_count) is not int or self.episode_action_count < 0
                or any(not isinstance(item, AdaptiveAttempt) for item in self.attempts)
                or not isfinite(self.original_start_beat) or self.original_start_beat < 0
                or self.original_end_beat is not None and (not isfinite(self.original_end_beat)
                    or self.original_end_beat <= self.original_start_beat)
                or self.source_attacks is not None and (type(self.source_attacks) is not int or self.source_attacks < 0)
                or self.attacks_per_beat is not None and (not isfinite(self.attacks_per_beat) or self.attacks_per_beat < 0)
                or self.reference_bpm is not None and (type(self.reference_bpm) is not int or self.reference_bpm < 1)):
            raise ValueError("Invalid source-bound adaptive context")


def adaptive_attempt_from_assessment(result, *, identity: str, start_beat: float,
                                     end_beat: float, bpm: int, phrase_start: float = 0.,
                                     assisted: bool = False, action: str = "repeat") -> AdaptiveAttempt:
    """Project the authoritative assignment; actual flags outrank priority status."""
    notes = tuple(entry for entry in getattr(result, "notes", ())
                  if start_beat <= entry.note.start - phrase_start < end_beat)
    def error_count(flag, statuses):
        if any(getattr(entry, "observation", None) is None and entry.status != "correct" for entry in notes):
            return None
        return sum(bool(getattr(entry.observation, flag)) if getattr(entry, "observation", None) is not None
                   else entry.status in statuses for entry in notes)
    return AdaptiveAttempt(identity, start_beat, end_beat, bpm,
        tuple(entry.note.start - phrase_start for entry in notes if entry.status == "wrong"),
        tuple(entry.note.start - phrase_start for entry in notes if entry.status == "missed"),
        error_count("timing_error", ("early", "late")), error_count("hold_error", ("short", "long")),
        getattr(result, "passed", None), assisted, action, getattr(result, "extra_notes", 0), bool(notes))


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
    context: AdaptiveContext | None = None


@dataclass(frozen=True)
class WholeEvidence:
    result: object
    phrase: object
    grid: tuple[float, ...]
    bpm: int
    minimum_bpm: int
    play_from_beat: float
    context: AdaptiveContext | None = None


@dataclass(frozen=True)
class RollingResponse:
    restart_beat: float
    end_beat: float
    bpm: int
    guided: bool
    count: int
    trouble_key: tuple
    mode: str
    action: str = "repair"
    reason: str = "registered_policy"


@dataclass(frozen=True)
class WholeResponse:
    bpm: int
    restart_beat: float
    mode: str
    end_beat: float | None = None
    guided: bool = False
    action: str = "repair"
    reason: str = "registered_policy"


_POLICIES = {
    policy.name: policy for policy in (
        MistakePolicy("adaptive", "Adaptive recovery",
                      "Two-measure rewind, "
                      f"{100 * (1 - SETTINGS.recovery_tempo_multiplier):g}% slowdown, "
                      "guided help after "
                      f"{SETTINGS.guided_recovery_after_failures} failures.",
                      True, SETTINGS.recovery_tempo_multiplier, 1.0, 2,
                      SETTINGS.guided_recovery_after_failures),
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


def mistake_policy_facts(policy: MistakePolicy) -> dict:
    """Serializable resolved values and implementation identity, never callables."""
    facts = {key: getattr(policy, key) for key in policy.__dataclass_fields__
             if not key.endswith("_handler")}
    facts["policy_id"] = facts.pop("name")
    for key in ("rolling_handler", "whole_handler"):
        handler = getattr(policy, key)
        code = getattr(handler, "__code__", None)
        facts[key] = (None if handler is None else {
            "module": getattr(handler, "__module__", type(handler).__module__),
            "implementation": getattr(handler, "__qualname__", type(handler).__qualname__),
            "bytecode_sha256": hashlib.sha256(code.co_code).hexdigest() if code else None})
    return facts


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
    context: AdaptiveContext | None = None,
) -> RollingResponse:
    """Return a metrical rewind; preserve source identity and learner history."""
    facts = RollingEvidence(
        decision, identity, bpm, minimum_bpm, previous_key, previous_count,
        tuple(grid), allow_guided, context)
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
            (chosen.guided and not allow_guided) or
            chosen.action not in {"repair", "continue", "repeat", "isolate", "slow", "guided", "reintegrate", "pause"} or
            chosen.action in {"continue", "pause"} and (chosen.bpm != bpm or chosen.guided)):
        raise ValueError("Invalid source-bound rolling response")
    return chosen


def whole_response(
    policy: MistakePolicy, result, *, phrase, grid: Sequence[float],
    bpm: int, minimum_bpm: int, play_from_beat: float,
    context: AdaptiveContext | None = None,
) -> WholeResponse:
    """Full-take recovery uses graded source attacks, not inferred timing."""
    facts = WholeEvidence(result, phrase, tuple(grid), bpm,
                          minimum_bpm, play_from_beat, context)
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
    reintegrating = (isinstance(chosen, WholeResponse) and chosen.action == "reintegrate"
                     and policy.whole_handler is not None and context is not None)
    maximum_bpm = (min(SETTINGS.maximum_bpm, max(bpm, context.reference_bpm or bpm))
                   if reintegrating else bpm)
    if (not isinstance(chosen, WholeResponse) or
            chosen.mode != policy.name or
            not minimum_bpm <= chosen.bpm <= maximum_bpm or
            chosen.restart_beat < (context.original_start_beat if reintegrating else play_from_beat) or
            chosen.restart_beat >= phrase.end - phrase.start or
            (chosen.restart_beat != play_from_beat and
             chosen.restart_beat not in facts.grid) or
            chosen.end_beat is not None and (chosen.end_beat not in facts.grid
                or chosen.end_beat <= chosen.restart_beat or chosen.end_beat > phrase.end - phrase.start) or
            chosen.action not in {"repair", "continue", "repeat", "isolate", "slow", "guided", "reintegrate", "pause"} or
            chosen.action in {"continue", "pause"} and (chosen.bpm != bpm or chosen.guided)):
        raise ValueError("Invalid source-bound whole-take response")
    return chosen


EVIDENCE_ADAPTIVE_VERSION = "evidence-adaptive-v1"
_EVIDENCE_POLICY = "evidence-adaptive"
_AUTOMATIC_ACTION_LIMIT = 12


def _adaptive_current(context: AdaptiveContext | None, grid, bpm):
    if context is None or not context.attempts:
        return None
    current = context.attempts[-1]
    end = context.original_end_beat if context.original_end_beat is not None else grid[-1]
    if (current.identity != context.identity or not current.reliable or current.bpm != bpm
            or not grid[0] <= context.original_start_beat <= current.start_beat < current.end_beat <= end <= grid[-1]
            or current.start_beat not in grid or current.end_beat not in grid):
        return None
    return current


def _comparable_suffix(context: AdaptiveContext, current: AdaptiveAttempt):
    result = []
    for attempt in reversed(context.attempts):
        if (attempt.identity != context.identity or not attempt.reliable or attempt.assisted
                or attempt.accepted is None or attempt.bpm != current.bpm
                or (attempt.start_beat, attempt.end_beat) != (current.start_beat, current.end_beat)):
            break
        result.append(attempt)
    return list(reversed(result))


def _strict_clean(attempt: AdaptiveAttempt) -> bool:
    return (attempt.accepted is True and not attempt.assisted and not attempt.wrong_beats
            and not attempt.missed_beats and attempt.timing_errors == 0
            and attempt.hold_errors == 0 and attempt.extra_errors == 0)


def _concentrated_measure(attempts, grid, start, end):
    """Two failures, >=3 actual pitch obligations, >=60% in one shared bar."""
    if len(attempts) < 2 or any(a.accepted is not False for a in attempts[-2:]):
        return None
    errors = [tuple(beat for beat in a.wrong_beats + a.missed_beats if start <= beat < end)
              for a in attempts[-2:]]
    total = sum(map(len, errors))
    if total < 3:
        return None
    candidates = []
    for left, right in zip(grid, grid[1:]):
        if left < start or right > end:
            continue
        counts = [sum(left <= beat < right for beat in beats) for beats in errors]
        if all(counts) and sum(counts) * 5 >= total * 3:
            candidates.append((sum(counts), left, right))
    if not candidates:
        return None
    # Earlier source position is the deterministic tie-break, not directory,
    # clock or note traversal order.
    _, left, right = min(candidates, key=lambda item: (-item[0], item[1]))
    return left, right


def _evidence_whole(facts: WholeEvidence) -> WholeResponse:
    context = facts.context
    current = _adaptive_current(context, facts.grid, facts.bpm)
    def response(action, reason, *, start=None, end=None, bpm=None, guided=False):
        return WholeResponse(facts.bpm if bpm is None else bpm,
            facts.play_from_beat if start is None else start, _EVIDENCE_POLICY,
            facts.grid[-1] if end is None else end, guided, action, reason)
    if current is None or current.start_beat != facts.play_from_beat:
        return response("repeat", "insufficient_comparable_evidence")
    original_start = context.original_start_beat
    original_end = context.original_end_beat if context.original_end_beat is not None else facts.grid[-1]
    focused = (current.start_beat, current.end_beat) != (original_start, original_end)
    if context.episode_action_count >= _AUTOMATIC_ACTION_LIMIT:
        return response("pause", "automatic_action_limit", start=current.start_beat, end=current.end_beat)
    if current.assisted:
        return response("isolate" if focused else "repeat", "guidance_requires_unsupported_retry",
                        start=current.start_beat, end=current.end_beat)
    comparable = _comparable_suffix(context, current)
    if focused and len(comparable) >= 2 and all(_strict_clean(a) for a in comparable[-2:]):
        left = max(0, facts.grid.index(current.start_beat) - 1)
        right = min(len(facts.grid) - 1, facts.grid.index(current.end_beat) + 1)
        return response("reintegrate", "two_clean_focused_outcomes",
            start=max(original_start, facts.grid[left]), end=min(original_end, facts.grid[right]),
            bpm=min(max(facts.bpm, context.reference_bpm or facts.bpm), facts.bpm + 5))
    if current.accepted is True:
        return response("continue" if not focused else "repeat", "full_target_progression" if not focused
                        else "focused_reassessment", start=current.start_beat, end=current.end_beat)
    if current.accepted is None or len(comparable) < 2:
        return response("repeat", "first_or_incomparable_failure", start=current.start_beat, end=current.end_beat)
    failures = []
    for attempt in reversed(comparable):
        if attempt.accepted is not False:
            break
        failures.append(attempt)
    if len(failures) < 2:
        return response("repeat", "new_failure_after_success", start=current.start_beat, end=current.end_beat)
    if any(a.action == "slow" for a in comparable) and len(failures) >= 2:
        return response("guided", "two_failures_at_slower_setting", start=current.start_beat,
                        end=current.end_beat, guided=True)
    if focused:
        return response("slow", "persistent_focused_failures", start=current.start_beat,
            end=current.end_beat, bpm=_scaled_bpm(facts.bpm, facts.minimum_bpm, .9))
    if len(failures) >= 3:
        # A sustain-safe runtime expansion can make an intended isolated bar
        # cover the original target. Do not endlessly choose an ineffective
        # smaller window: these remain actual full-target failed exposures.
        return response("slow", "persistent_full_target_failures",
                        bpm=_scaled_bpm(facts.bpm, facts.minimum_bpm, .9))
    cluster = _concentrated_measure(comparable[-2:], facts.grid, current.start_beat, current.end_beat)
    if cluster is not None:
        return response("isolate", "repeated_concentrated_pitch_errors", start=cluster[0], end=cluster[1])
    density = context.attacks_per_beat
    if density is None:
        onsets = {round(note.start, 7) for note in getattr(facts.phrase, "notes", ())}
        density = len(onsets) / (original_end - original_start)
    persistent_rhythm = all((a.timing_errors or 0) + (a.hold_errors or 0) > 0 for a in comparable[-2:])
    if density * facts.bpm / 60 >= 4 and persistent_rhythm:
        return response("slow", "persistent_timing_under_source_load",
                        bpm=_scaled_bpm(facts.bpm, facts.minimum_bpm, .9))
    return response("repeat", "scattered_errors_require_full_target_reassessment")


def _evidence_rolling(facts: RollingEvidence) -> RollingResponse:
    context = facts.context
    current = _adaptive_current(context, facts.grid, facts.bpm)
    start, end = facts.decision.restart_beat, facts.decision.end_beat
    if current is not None and current.end_beat != end:
        current = None
    action, reason = "continue", "insufficient_comparable_evidence"
    if current is not None and context.identity == facts.identity:
        if context.episode_action_count >= _AUTOMATIC_ACTION_LIMIT:
            action, reason = "pause", "automatic_action_limit"
        elif not current.assisted and current.accepted is False:
            prior = next((a for a in reversed(context.attempts[:-1])
                if a.identity == context.identity and a.bpm == current.bpm
                and a.start_beat <= current.start_beat and a.end_beat >= current.end_beat), None)
            if prior is not None and (not prior.reliable or prior.assisted or prior.accepted is None):
                prior = None
            cluster = (_concentrated_measure((prior, current), facts.grid, current.start_beat, current.end_beat)
                       if prior is not None else None)
            if cluster is not None and start <= cluster[0] < cluster[1] == end:
                start = cluster[0]
                action, reason = "isolate", "repeated_concentrated_pitch_errors"
            else:
                reason = "terminal_feedback_for_scattered_or_first_errors"
    key = facts.identity, start, end
    count = facts.previous_count + 1 if facts.previous_key == key else 1
    return RollingResponse(start, end, facts.bpm, False, count, key,
                           _EVIDENCE_POLICY, action, reason)


register_mistake_policy(MistakePolicy(
    _EVIDENCE_POLICY, "Evidence-guided recovery",
    "Use source-bound error patterns and comparable retry outcomes to repeat, isolate, slow, guide and reintegrate; pause after twelve automatic actions.",
    True, 1., 1., 1, None, rolling_handler=_evidence_rolling, whole_handler=_evidence_whole,
    version=EVIDENCE_ADAPTIVE_VERSION))

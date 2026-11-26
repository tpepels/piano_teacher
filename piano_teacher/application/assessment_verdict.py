"""Single policy-specific verdict used by teaching and durable settlement.

Canonical note observations remain unchanged; the chosen course policy
decides exactly once which consequences that result is eligible to earn.
No second consumer may inspect a generic assessment property to
override a flow-specific decision.
"""
from __future__ import annotations
from dataclasses import dataclass
from ..lesson_settings import SETTINGS

@dataclass(frozen=True, slots=True)
class AssessmentVerdict:
    policy: str
    accepted: bool
    clean: bool
    clears_trouble: bool
    source_note_count: int
    extra_notes: int
    ignored: bool = False

    @staticmethod
    def decide(result, *, policy: str, eligible: bool) -> "AssessmentVerdict":
        if policy not in {"practice-flow", "standard"}:
            raise ValueError("Unknown assessment acceptance policy")
        accepted = bool(result and
            (result.flow_passed if policy == "practice-flow" else result.passed))
        # A zero threshold is deliberately disabled. The existing note,
        # onset and optional release checks must still pass independently.
        threshold = SETTINGS.minimum_accuracy_percent
        if accepted and policy == "practice-flow" and threshold > 0.0:
            accepted = result.accuracy_percent >= threshold
        ignored = bool(policy == "practice-flow" and result and result.notes
                       and result.accuracy_percent < SETTINGS.ignored_accuracy_below_percent)
        accepted = accepted and not ignored
        clean = bool(result and result.clean and not ignored)
        return AssessmentVerdict(
            policy=policy, accepted=accepted,
            clean=clean, clears_trouble=bool(eligible and accepted),
            source_note_count=len(result.notes) if result else 0,
            extra_notes=result.extra_notes if result else 0, ignored=ignored)

"""Single policy-specific verdict used by teaching and durable settlement.

Canonical note observations remain unchanged; the chosen course policy
decides exactly once which consequences that result is eligible to earn.
No second consumer may inspect a generic assessment property to
override a flow-specific decision.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class AssessmentVerdict:
    policy: str
    accepted: bool
    clean: bool
    clears_trouble: bool
    source_note_count: int
    extra_notes: int

    @staticmethod
    def decide(result, *, policy: str, eligible: bool) -> "AssessmentVerdict":
        if policy not in {"practice-flow", "standard"}:
            raise ValueError("Unknown assessment acceptance policy")
        accepted = bool(result and
            (result.flow_passed if policy == "practice-flow" else result.passed))
        clean = bool(result and result.clean)
        return AssessmentVerdict(
            policy=policy, accepted=accepted,
            clean=clean, clears_trouble=bool(eligible and accepted),
            source_note_count=len(result.notes) if result else 0,
            extra_notes=result.extra_notes if result else 0)

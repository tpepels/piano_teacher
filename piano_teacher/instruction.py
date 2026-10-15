"""Student-facing decisions around the existing timed assessment policy."""
from __future__ import annotations


def next_full_attempt(plan, result) -> str:
    """Describe the pending decision without applying or crediting it early."""
    if not result.clean:
        return "Let's try the whole passage again."
    if plan.bpm < plan.target_bpm:
        following = min(plan.target_bpm, max(plan.bpm + 1, round(plan.bpm * 1.10)))
        return f"Clean passage — restore tempo to {following} BPM toward {plan.target_bpm} BPM."
    streak = plan.streak + 1
    if streak < 3:
        return f"Clean pass {streak}/3 — play the whole passage again."
    if plan.variant_index + 1 < len(plan.variants):
        following = plan.variants[plan.variant_index + 1]
        if any(sum(abs(other.start-note.start) < 1e-6 for other in following.notes) > 1
               for note in following.notes):
            action = "now restore missing chord notes"
        elif following.level == "original":
            action = "now play all the notes"
        else:
            action = "now add more melody notes"
    elif plan.hand_index + 1 < len(plan.hands):
        hand = plan.hands[plan.hand_index + 1]
        action = "now play both hands together" if hand == "both" else f"now learn the {hand} hand"
    elif plan.index + 1 < len(plan.exercises):
        action = "now learn the next passage"
    else:
        action = "passage mastered"
    return f"Clean pass 3/3 — {action}."

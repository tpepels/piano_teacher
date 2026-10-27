"""Read-only presentation of practice facts. No engine or renderer imports."""
from __future__ import annotations
from collections.abc import Collection, Iterable, Mapping


def hand_stage_rows(*, kind: str, exercise_index: int, current_hand: str,
                    available_hands: Collection[str], mastered: Collection[str],
                    lesson_steps: Iterable[tuple[int, str, str]],
                    builtin_warmup: bool) -> list[dict]:
    if kind not in ("learn", "warmup"):
        return []
    steps = tuple(lesson_steps)
    rows = []
    for hand in ("right", "left", "both"):
        matching = [key for index, step_hand, key in steps
                    if index == exercise_index and step_hand == hand]
        if not matching:
            continue
        complete = all(key in mastered for key in matching)
        locked = (builtin_warmup and hand != "right"
                  and not all(previous["complete"] for previous in rows))
        rows.append({"hand":hand, "active":hand == current_hand,
                     "complete":complete, "locked":locked,
                     "available":hand in available_hands})
    return rows


def guided_learning_fields(*, teaching: Mapping, fragment: Mapping, session_id: int,
                           has_more_units: bool, returning: bool, phase: str,
                           required_notes: int, duration_beats: float) -> dict:
    """Project a captured teaching snapshot; never sample clocks or change state."""
    snapshot = dict(teaching)
    snapshot["fragment"] = dict(fragment)
    snapshot["session_id"] = session_id
    snapshot["has_more_units"] = has_more_units
    feedback = str(snapshot.get("feedback", "Find the highlighted notes at your own pace."))
    fields = {}
    if phase == "loading":
        feedback = "Preparing a short idea to learn"
    elif phase == "disconnected":
        feedback = "No piano connected — timed preview only. Connect your piano in Settings to learn notes."
        fields["next_action"] = "Connect your piano in Settings to learn notes."
    elif phase == "guided_complete":
        feedback = "You found every note. Ready to add rhythm?"
        fields["next_action"] = ("Retry rhythm from these bars." if returning
                                  else "Ready to add rhythm? Choose Practice.")
        if has_more_units:
            feedback = "You found this idea. Continue with the next short idea."
            fields["next_action"] = "Choose Next idea to learn the next part of the passage."
    elif phase == "paused":
        feedback = "Paused — resume when you are ready."
    elif phase == "guided_wait":
        labels = list(dict.fromkeys(n["label"] for n in snapshot.get("expected_notes", [])))
        keys = " + ".join(labels)
        together = " together" if len(labels) > 1 else ""
        feedback = f"Play {keys}{together}. Take your time."
        if snapshot.get("hint_reason") == "wrong_note":
            feedback = f"Find {keys} on the keyboard below, then try again."
        elif snapshot.get("target_index", 0) > 0:
            feedback = "Good. Next: " + keys + together + "."
    fields.update(teaching=snapshot, phase=phase, running=False,
                  paused=phase == "paused", clock_beat=0.0, countdown=0.0,
                  first_bar=fragment["first_bar"], last_bar=fragment["last_bar"],
                  required_notes=required_notes, duration_beats=duration_beats,
                  progress=snapshot.get("target_index", 0)/max(1, snapshot.get("target_count", 0)),
                  feedback=feedback, feedback_unmapped=0)
    return fields

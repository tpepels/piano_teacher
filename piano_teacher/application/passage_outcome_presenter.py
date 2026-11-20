"""Pure, immutable presentation of one already-chosen teaching verdict.

No LearningPlan mutation, timer selection, grading, persistence or new
decisions. User text is a projection of the existing single teaching result.
"""
from __future__ import annotations

from dataclasses import replace
from ..application import practice_flow
from ..lesson_settings import SETTINGS


def teaching_instruction(pending) -> str:
    decision,state = pending.decision,pending.state
    if decision.progress_after.cursor == state.progress.cursor:
        return ("passage mastered"
                if decision.flow_outcome is practice_flow.Outcome.PIECE_DONE
                else "play the passage again")
    chosen = replace(state.course,definition=decision.definition_after,
                     progress=decision.progress_after)
    if chosen.progress.cursor[0] != state.progress.cursor[0]:
        return "now learn the next passage"
    if chosen.hand != state.course.hand:
        return ("now play both hands together" if chosen.hand == "both"
                else f"now learn the {chosen.hand} hand")
    notes = chosen.stage.variant.notes
    if any(sum(abs(other.start-note.start)<1e-6 for other in notes)>1
           for note in notes):
        return "now restore missing chord notes"
    return ("now play all the notes" if chosen.stage.variant.level == "original"
            else "now add more melody notes")


def next_action(pending, *, target_bpm: float, start_beat: float,
                assessed_bpm: float | None) -> str:
    decision = pending.decision
    response = decision.response
    if decision.verdict is not None and decision.verdict.accepted:
        label = "Clean" if decision.verdict.clean else "Accepted"
        if pending.state.progress.bpm < pending.state.progress.target_bpm:
            message = (f"{label} passage — restore tempo to "
                       f"{decision.progress_after.bpm} BPM toward {target_bpm} BPM.")
        else:
            message = (
                f"{label} pass {pending.state.progress.streak+1}/"
                f"{SETTINGS.clean_runs_to_master} — {teaching_instruction(pending)}.")
    else:
        message = ("Retry the whole passage (red errors or at least half "
                   "the attacks yellow).")
    if response is not None and response.restart_beat > start_beat+1e-7:
        return (f"Repeat the difficult measure at {response.bpm} BPM, "
                "then play the whole passage.")
    if (response is not None and assessed_bpm is not None
            and response.bpm < assessed_bpm):
        return f"Retry more slowly at {response.bpm} BPM."
    return message

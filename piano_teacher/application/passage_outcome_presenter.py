"""Pure, immutable presentation of one already-chosen teaching verdict.

No LearningPlan mutation, timer selection, grading, persistence or new
decisions. User text is a projection of the existing single teaching result.
"""
from __future__ import annotations

from dataclasses import replace
from ..application import practice_flow


def teaching_instruction(pending) -> str:
    decision,state = pending.decision,pending.state
    if decision.progress_after.position == state.progress.position:
        return ("passage mastered"
                if decision.flow_outcome is practice_flow.Outcome.PIECE_DONE
                else "play the passage again")
    chosen = replace(state.course,definition=decision.definition_after,
                     progress=decision.progress_after)
    if chosen.step.exercise_index != state.course.step.exercise_index:
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
    if decision.verdict and decision.verdict.ignored:
        return "Repeat at the same tempo."
    if pending.state.course.profile == "sight-reading":
        return "Open Sight reading to start a new random round, or Play to repeat this one."
    if decision.flow_outcome is practice_flow.Outcome.HAND_REVIEW or pending.state.progress.hand_review is not None:
        return decision.message
    if decision.flow_outcome is practice_flow.Outcome.SECTION_READY:
        return "Section complete · C to repeat · F for next section."
    if decision.verdict is not None and decision.verdict.accepted:
        label = "Clean" if decision.verdict.clean else "Accepted"
        if pending.state.progress.bpm < pending.state.progress.target_bpm:
            if decision.progress_after.tempo_clean:
                return f"{label} passage — once more at {decision.progress_after.bpm} BPM."
            message = (f"{label} passage — restore tempo to "
                       f"{decision.progress_after.bpm} BPM toward {target_bpm} BPM.")
        else:
            message = (
                f"{label} pass {pending.state.progress.streak+1}/"
                f"{pending.state.course.clean_runs_required} — {teaching_instruction(pending)}.")
    else:
        message = ("Retry the whole passage (red errors or at least half "
                   "the attacks yellow).")
    return message


def performance_next_action(*, summary: dict) -> str:
    return ("Review your performance, then Practice the weakest section."
        if summary["weakest_bars"] else
        "Clean performance. Choose Practice to build your clean-run streak.")

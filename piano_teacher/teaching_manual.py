"""Learner commands -> the course after them and the exposure they start.

Inputs are immutable course progress and validated scalar intent; no engine,
database, clock or renderer. Free always covers the whole selected window
(practice_flow_course.decide widens any learn exposure to it).
"""
from dataclasses import dataclass
from .teaching_course import manual_progress, at_position, next_unmastered
from .course_navigation import choose_source_opening


@dataclass(frozen=True, slots=True)
class ManualFacts:
    paused: bool = False
    source_changed: bool = False
    open_from_beat: float = 0.
    pending_rewind: float | None = None


def choose_manual(event, state):
    c, route, facts = state.course, state.route, state.manual_facts
    action = event.action
    mode, start, end = route.mode, facts.open_from_beat, None
    continuation = "continue"
    if event.manual is not None:
        m = event.manual
        c = manual_progress(c, m.action, number=m.number, hand=m.hand, bpm=m.bpm)
        if route.mode == "learn":
            continuation, start = "guided", 0.
    elif action in ("section_repeat", "section_next"):
        following = next_unmastered(c)
        if (c.key not in dict(c.progress.mastered) or following is None
                or c.steps[following].exercise_index == c.step.exercise_index):
            raise ValueError("No completed section awaiting a choice")
        if action == "section_next":
            c = at_position(c, following)
        c = c.with_progress(bpm=c.progress.target_bpm, streak=0, failures=0)
        mode = "practice" if action == "section_repeat" or c.exercise.kind == "perform" else "learn"
        continuation = "guided" if mode == "learn" else "continue"
        start, end = (0.0 if mode == "learn" else c.stage.variant.phrase.first_attack_beat), None
    elif action in ("stop", "pause"):
        continuation = action
    elif action == "open_at":
        target = choose_source_opening(c, bar=event.bar, mode=event.requested_mode or "learn")
        c = manual_progress(c, "select", number=target.exercise_index)
        start = c.piece.bar_boundaries[target.bar-1]-c.stage.variant.phrase.start
        mode = target.mode
        continuation = "guided" if mode == "learn" else "continue"
    elif action == "perform":
        if event.scope not in (None, "current", "whole"):
            raise ValueError("Choose the current passage or whole piece")
        if event.scope == "whole":
            index = next((i for i, ex in reversed(tuple(enumerate(c.definition.exercises))) if ex.kind == "perform"), 0)
            c = manual_progress(c, "select", number=index)
            if "both" in c.hands:
                c = manual_progress(c, "hand", hand="both")
            c = c.with_progress(bpm=state.progress.bpm)
        mode = "perform"
    elif action in ("learn", "learn_retry", "course_stage"):
        mode, continuation = "learn", "guided"
        start = event.from_beat if event.from_beat is not None else 0.
        if c.exercise.kind == "perform" and action != "learn":
            # The final test has no Free of its own; it runs in Tempo.
            mode, continuation, start = "perform", "continue", 0.
    elif action in ("practice", "start", "restart", "resume", "listen"):
        mode = "listen" if action == "listen" else "practice" if action == "practice" or route.mode == "learn" else route.mode
        if event.requested_mode is not None:
            mode = event.requested_mode
        if event.from_beat is not None:
            start = event.from_beat
        elif action == "restart":
            start = facts.pending_rewind if facts.pending_rewind is not None else route.from_beat
        if mode == "listen":
            start,end = 0.,None
        if route.guided_return and route.guided_return[0] == c.key and mode == "practice":
            start = route.guided_return[1]
            end = None
    if end is not None and end >= c.stage.variant.phrase.end-c.stage.variant.phrase.start-1e-7 and mode != "learn":
        end = None
    return c, start, end, mode, continuation

"""Manual source/exposure choices owned by lesson generators.

Inputs are immutable source-local credits and validated scalar intent. This
module does not know about an engine, database, clock or renderer.
"""
from dataclasses import dataclass
from .teaching_course import manual_progress
from .learner_state import guided_units
from .course_navigation import choose_source_opening
from .measure_grid import phrase_grid
from .application.guided_fragment import select_guided_fragment


@dataclass(frozen=True, slots=True)
class GuidedCredits:
    stage_key: str
    resume: tuple | None = None
    completed: tuple[tuple, ...] = ()


@dataclass(frozen=True, slots=True)
class ManualFacts:
    credits: tuple[GuidedCredits, ...] = ()
    paused: bool = False
    guidance_completed: bool = False
    source_changed: bool = False
    open_from_beat: float = 0.
    pending_rewind: float | None = None


def unit_key(unit):
    return (unit["start_beat"], unit["end_beat"], tuple(unit["source_indices"]))


def next_guided_range(course, credits, *, explicit=False):
    units = guided_units(course.stage.variant, course.piece.bar_boundaries)
    saved = next((entry for entry in credits if entry.stage_key == course.key), GuidedCredits(course.key))
    selected = next((unit for unit in units if unit_key(unit) == saved.resume), None)
    if selected is None:
        selected = next((unit for unit in units if unit_key(unit) not in saved.completed), None)
    if selected is None and explicit:
        selected = next(iter(units), None)
    return None if selected is None else (selected["start_beat"], selected["end_beat"])


def choose_manual(event, state):
    c, route, facts = state.course, state.route, state.manual_facts
    action = event.action
    mode, start, end = route.mode, facts.open_from_beat, None
    continuation = "continue"
    if event.manual is not None:
        m = event.manual
        c = manual_progress(c, m.action, number=m.number, hand=m.hand, bpm=m.bpm)
        if route.mode == "learn":
            continuation = "guided"
            if m.tempo_only and route.guided_range:
                start, end = route.guided_range
            elif route.course_guided and c.exercise.kind == "perform" and m.action != "hand":
                mode, continuation, start = "perform", "continue", 0.
            else:
                selected = next_guided_range(c, facts.credits, explicit=m.action == "hand") if route.course_guided else None
                if selected:
                    start, end = selected
                elif route.course_guided:
                    mode, continuation, start = "practice", "continue", 0.
                else:
                    start = 0.
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
            h = c.hands.index("both") if "both" in c.hands else 0
            variants = c.definition.stages(c.exercise, c.hands[h])
            c = c.with_progress(cursor=(index,h,len(variants)-1), bpm=state.progress.bpm)
        mode = "perform"
    elif action == "seek":
        if not facts.paused:
            raise ValueError("Pause before choosing a source bar")
        phrase = c.stage.variant.phrase
        if type(event.bar) is not int or not phrase.first_bar <= event.bar <= phrase.last_bar:
            raise ValueError("Choose a whole bar number inside the active passage")
        start = phrase_grid(phrase,c.piece.bar_boundaries)[event.bar-phrase.first_bar]
        # A source-bar seek from Perform starts a graded *Practice* passage.
        # The score-ready acknowledgement consumes this same exposure, so
        # retaining mode="perform" here would silently re-enter Perform and
        # award a performance review for a partial practice take.
        mode = "learn" if route.mode == "learn" else "practice"
        continuation = "guided" if mode == "learn" else "continue"
    elif action in ("learn", "learn_retry", "learn_next", "course_stage"):
        if action == "learn_next" and not facts.guidance_completed:
            raise ValueError("Find the current notes before continuing to the next idea")
        mode, continuation = "learn", "guided"
        if action == "learn_next" and route.guided_return is not None:
            mode, continuation = "practice", "reintegrate"
            start = route.guided_return[1]
            end = None
        elif event.from_beat is not None:
            start = event.from_beat
        elif action == "learn_retry":
            start = route.guided_range[0] if route.guided_range else 0.
        elif c.exercise.kind == "perform" and action != "learn":
            mode, continuation, start = "perform", "continue", 0.
        else:
            selected = next_guided_range(c,facts.credits,explicit=action == "learn")
            if selected:
                start, end = selected
            else:
                mode, continuation, start = "practice", "continue", 0.
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
    if mode == "learn" and continuation == "guided":
        fragment = select_guided_fragment(c.stage.variant.phrase,c.piece.bar_boundaries,start)
        start,end = fragment.start,fragment.end
    if end is not None and end >= c.stage.variant.phrase.end-c.stage.variant.phrase.start-1e-7 and mode != "learn":
        end = None
    return c, start, end, mode, continuation

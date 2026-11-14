"""Manual source/exposure choices owned by lesson generators.

Inputs are immutable source-local credits and validated scalar intent. This
module does not know about an engine, database, clock or renderer.
"""
from dataclasses import dataclass, replace
from .teaching_course import manual_progress, steps, select_cursor
from .lesson_generators import lesson_hands
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
    trouble: tuple[tuple, ...] = ()  # stage, start, end, source indices
    review: tuple[tuple, ...] = ()   # first/last bar, start/end beat, errors
    review_current: bool = False
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
        target = choose_source_opening(c, bar=event.bar, mode=event.requested_mode or "learn", warmup=route.warmup)
        c = manual_progress(c, "select", number=target.exercise_index)
        start = c.piece.bar_boundaries[target.bar-1]-c.stage.variant.phrase.start
        mode = target.mode
        continuation = "guided" if mode == "learn" else "continue"
    elif action == "skip_stage":
        if route.warmup:
            raise ValueError("Warm-up stages unlock after three clean runs, not skips")
        options = steps(c)
        index = next(i for i, step in enumerate(options) if step[3] == c.key)
        if not isinstance(event.reason, str) or not event.reason.strip() or index+1 >= len(options):
            raise ValueError("Choose an available next step and explain the skip")
        c = manual_progress(c, "select_step", number=index+2)
        # A whole-piece Perform step is an actual performance assessment.
        # It has no guided note-finding phase, even when reached by explicit
        # skips from an earlier learning stage.
        if c.exercise.kind == "perform":
            mode, continuation, start, end = "perform", "continue", 0., None
        else:
            mode, continuation = "learn", "guided"
            selected = next_guided_range(c, facts.credits)
            if selected:
                start, end = selected
            else:
                mode, continuation, start = "practice", "continue", 0.
    elif action == "place_original":
        if route.warmup:
            raise ValueError("Warm-up stages unlock after three clean runs")
        if c.stage.variant.level == "original":
            raise ValueError("You are already playing the original notes")
        v = next(i for i, stage in enumerate(c.stages) if stage.variant.level == "original")
        c = select_cursor(c, (*c.progress.cursor[:2], v))
        mode, continuation = "learn", "guided"
        selected = next_guided_range(c, facts.credits)
        if selected:
            start, end = selected
        else:
            mode, continuation, start = "practice", "continue", 0.
    elif action == "revisit_trouble":
        entry = next((u for u in facts.trouble if u[0] == event.requested_stage and u[1] == event.from_beat), None)
        target = next((step for step in steps(c) if step[3] == event.requested_stage), None)
        if entry is None or target is None:
            raise ValueError("This trouble spot is no longer available")
        c = select_cursor(c, target[:3]).with_progress(bpm=state.progress.bpm)
        start, end = entry[1:3]
        mode, continuation = "learn", "guided"
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
    elif action in ("review_retry", "practice_weak"):
        if not facts.review_current or not facts.review:
            raise ValueError("Finish an assessed attempt before retrying a section")
        selected = (facts.review[0] if action == "practice_weak" else
            next((u for u in facts.review if u[:2] == (event.first_bar,event.last_bar)), None))
        if selected is None or selected[4] <= 0:
            raise ValueError("Choose a difficult section from the latest assessment")
        start, end = selected[2:4]
        mode = "practice"
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
            end = route.guided_range[1] if state.policy.whole_handler is not None and route.guided_range else None
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
            end = route.guided_range[1] if state.policy.whole_handler is not None and route.guided_range else None
    if mode == "learn" and continuation == "guided":
        fragment = select_guided_fragment(c.stage.variant.phrase,c.piece.bar_boundaries,start)
        start,end = fragment.start,fragment.end
    if end is not None and end >= c.stage.variant.phrase.end-c.stage.variant.phrase.start-1e-7 and mode != "learn":
        end = None
    return c, start, end, mode, continuation

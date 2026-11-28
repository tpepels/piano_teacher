"""The Practice Flow course as a list of steps with a cursor.

A piece's course is one immutable, ordered list of steps (measure window x
hand), built once from its definition. Progress is a position in that list
plus a small record: the current step's tempo, failures and clean takes, the
mastered steps, and how often each step went back to Free. What happens
*within* a step (Listen, Free, aid, Tempo) is application/practice_flow.py;
moving the cursor is decided only by practice_flow_course.decide.

Saved keys ("course:2:practice-flow:<window>:<hand>:<level>:<sig>") are the
step identities; they never change for the same source.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import hashlib
import json
from .lesson_contracts import LessonPlanDefinition, lesson_hands
from .lesson_settings import SETTINGS, course_rules
from .music import Piece


@dataclass(frozen=True, slots=True)
class Step:
    """One entry of the course list."""
    exercise_index: int
    hand: str
    key: str
    kind: str
    first_bar: int
    last_bar: int
    level: str
    required_notes: int


@dataclass(frozen=True, slots=True)
class PlanProgress:
    position: int
    bpm: int
    target_bpm: int
    streak: int
    failures: int
    mastered: tuple[tuple[str, int], ...]
    free_returns: tuple[tuple[str, int], ...] = ()
    tempo_failures: tuple[tuple[str, int, int], ...] = ()
    tempo_clean: int = 0
    both_failures: int = 0
    # (original both-hand step key, review/return BPM, consecutive passes)
    hand_review: tuple[str, int, int] | None = None


def stage_key(exercise, hand, variant, profile, version):
    phrase = variant.phrase
    events = [(n.start-phrase.start, n.end-phrase.start, n.pitch, n.track, n.channel, n.hand)
              for n in phrase.notes]
    signature = hashlib.sha256(json.dumps((phrase.end-phrase.start, events),
        separators=(",", ":")).encode()).hexdigest()[:16]
    return f"course:{version}:{profile}:{exercise.key}:{hand}:{variant.level}:{signature}"


_steps_cache: dict[int, tuple] = {}


def course_steps(definition: LessonPlanDefinition, profile: str, version: int) -> tuple[Step, ...]:
    """The ordered step list: each window's hands in order, then the next
    window, ending with the final test. Cached per immutable definition."""
    cached = _steps_cache.get(id(definition))
    if cached is not None and cached[0] is definition and cached[1] == (profile, version):
        return cached[2]
    steps = []
    for index, exercise in enumerate(definition.exercises):
        for hand in lesson_hands(exercise):
            variant = definition.stages(exercise, hand)[0].variant
            steps.append(Step(index, hand,
                stage_key(exercise, hand, variant, profile, version), exercise.kind,
                exercise.phrase.first_bar, exercise.phrase.last_bar,
                variant.level, len(variant.notes)))
    steps = tuple(steps)
    if len(_steps_cache) > 4:
        _steps_cache.clear()
    _steps_cache[id(definition)] = (definition, (profile, version), steps)
    return steps


@dataclass(frozen=True, slots=True)
class CourseState:
    piece: Piece
    definition: LessonPlanDefinition
    progress: PlanProgress
    profile: str
    course_version: int

    @property
    def steps(self) -> tuple[Step, ...]:
        return course_steps(self.definition, self.profile, self.course_version)

    @property
    def step(self) -> Step:
        return self.steps[self.progress.position]

    @property
    def exercises(self):
        return self.definition.exercises

    @property
    def exercise(self):
        return self.definition.exercises[self.step.exercise_index]

    @property
    def hands(self):
        return lesson_hands(self.exercise)

    @property
    def hand(self):
        return self.step.hand

    @property
    def clean_runs_required(self):
        return course_rules().clean_runs_to_master

    @property
    def stage(self):
        return self.definition.stages(self.exercise, self.hand)[0]

    @property
    def key(self):
        return self.step.key

    def with_progress(self, **changes):
        return replace(self, progress=replace(self.progress, **changes))


def floor_bpm(course) -> int:
    from .application.practice_flow import floor_bpm as floor
    return floor(int(course.progress.target_bpm))


def at_position(course, position: int):
    """Move the cursor. A step always begins without tempo history: Listen
    and Free run at the target, Tempo restarts at 50% (practice_flow)."""
    if type(position) is not int or not 0 <= position < len(course.steps):
        raise ValueError("Lesson step out of bounds")
    return course.with_progress(position=position, bpm=course.progress.target_bpm,
                                streak=0, failures=0, tempo_clean=0, both_failures=0,
                                hand_review=None)


def next_unmastered(course) -> int | None:
    """The next step not yet mastered: forward from here, then from the
    start (after a jump back, mastered windows are skipped)."""
    mastered = dict(course.progress.mastered)
    steps = course.steps
    here = course.progress.position
    for index in (*range(here+1, len(steps)), *range(0, here)):
        if steps[index].key not in mastered:
            return index
    return None


def position_of(course, exercise_index: int, hand: str | None = None) -> int:
    """The step for a window (its first hand, or the named one)."""
    for index, step in enumerate(course.steps):
        if step.exercise_index == exercise_index and (hand is None or step.hand == hand):
            return index
    raise ValueError(f"Hand {hand!r} unavailable" if hand else "Exercise index out of bounds")


def manual_progress(course, action, *, number=None, hand=None, bpm=None):
    """Learner navigation and tempo, each a plain cursor or tempo change."""
    p = course.progress
    if action == "select_step":
        if type(number) is not int or not 1 <= number <= len(course.steps):
            raise ValueError("Lesson step out of bounds")
        return course if number-1 == p.position else at_position(course, number-1)
    if action == "select":
        if type(number) is not int or not 0 <= number < len(course.exercises):
            raise ValueError("Exercise index out of bounds")
        return at_position(course, position_of(course, number))
    if action in ("next", "previous"):
        index = min(len(course.exercises)-1, max(0,
            course.step.exercise_index + (1 if action == "next" else -1)))
        return at_position(course, position_of(course, index))
    if action == "hand":
        if hand not in course.hands:
            raise ValueError(f"Hand {hand!r} unavailable")
        return at_position(course, position_of(course, course.step.exercise_index, hand))
    if action == "tempo":
        # Practice Flow's target is always the source tempo.
        if type(bpm) not in (int, float) or not 1 <= bpm <= SETTINGS.maximum_bpm:
            raise ValueError(f"BPM must be between 1 and {SETTINGS.maximum_bpm}")
        target = course.piece.bpm
        return course.with_progress(bpm=min(int(bpm), target), target_bpm=target,
                                    streak=0, failures=0, tempo_clean=0)
    step = SETTINGS.manual_tempo_step_bpm
    if action == "tempo_up" and p.bpm < p.target_bpm:
        return course.with_progress(bpm=min(p.target_bpm, p.bpm+step), streak=0, failures=0, tempo_clean=0)
    if action == "tempo_down" and p.bpm > floor_bpm(course):
        return course.with_progress(bpm=max(floor_bpm(course), p.bpm-step), streak=0, failures=0, tempo_clean=0)
    return course

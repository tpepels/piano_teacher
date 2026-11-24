"""Pure course progression over immutable source definitions and progress.

These are the course algorithms, shared by generator authority and the public
plan API. No operation constructs or mutates a LearningPlan.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import hashlib
import json
import math
from .lesson_contracts import LessonPlanDefinition, lesson_hands
from .lesson_settings import SETTINGS, course_rules
from .music import Piece
from .tempo_difficulty import suggested_start_bpm
from .repeated_passages import exact_repetition_signature


@dataclass(frozen=True, slots=True)
class PlanProgress:
    cursor: tuple[int, int, int]
    bpm: int
    target_bpm: int
    streak: int
    failures: int
    mastered: tuple[tuple[str, int], ...]
    stage_tempos: tuple[tuple[str, int], ...]
    transferable_tempos: tuple[str, ...]
    free_returns: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class CourseState:
    piece: Piece
    definition: LessonPlanDefinition
    progress: PlanProgress
    profile: str
    course_version: int

    @property
    def exercises(self):
        return self.definition.exercises

    @property
    def exercise(self):
        return self.definition.exercises[self.progress.cursor[0]]

    @property
    def hands(self):
        return lesson_hands(self.exercise)

    @property
    def hand(self):
        return self.hands[self.progress.cursor[1]]

    @property
    def clean_runs_required(self):
        return course_rules().clean_runs_to_master

    @property
    def stages(self):
        return self.definition.stages(self.exercise, self.hand)

    @property
    def stage(self):
        return self.stages[self.progress.cursor[2]]

    @property
    def key(self):
        return stage_key(self.exercise, self.hand, self.stage.variant,
                         self.profile, self.course_version)

    def with_progress(self, **changes):
        return replace(self, progress=replace(self.progress, **changes))


def stage_key(exercise, hand, variant, profile, version):
    phrase = variant.phrase
    events = [(n.start-phrase.start, n.end-phrase.start, n.pitch, n.track, n.channel, n.hand)
              for n in phrase.notes]
    signature = hashlib.sha256(json.dumps((phrase.end-phrase.start, events),
        separators=(",", ":")).encode()).hexdigest()[:16]
    return f"course:{version}:{profile}:{exercise.key}:{hand}:{variant.level}:{signature}"


def steps(course):
    return tuple((i, h, v, stage_key(ex, hand, stage.variant, course.profile,
                 course.course_version))
                 for i, ex in enumerate(course.definition.exercises)
                 for h, hand in enumerate(lesson_hands(ex))
                 for v, stage in enumerate(course.definition.stages(ex, hand)))


def start_bpm(course):
    p = course.progress
    baseline = min(p.target_bpm, max(SETTINGS.minimum_bpm, SETTINGS.start_tempo_bpm))
    return min(p.target_bpm, suggested_start_bpm(course.stage.variant.phrase, course.hand,
        default_bpm=baseline, minimum_bpm=SETTINGS.minimum_bpm))


def minimum_bpm(course):
    from .application.practice_flow import floor_bpm
    return floor_bpm(int(course.progress.target_bpm))


def maximum_bpm(course):
    """The highest tempo the selected course allows its manual controls."""
    return min(SETTINGS.maximum_bpm, course.progress.target_bpm)


def carried_bpm(course):
    """Reuse earned tempo only when this stage has the same actual source ink.

    A mastered skeleton's speed does not prove that an outline containing
    more attacks (or a changed rhythmic exercise) can be played at that speed.
    Each genuinely new source task starts its own difficulty-adjusted ladder.
    Distinct lessons containing an exactly repeated passage still share
    earned tempo through tempo_for_stage(), with independent assessment.
    """
    p = course.progress
    tempos = dict(p.stage_tempos)
    current_notes = course.stage.variant.notes
    earned = [
        stage.effective_bpm(tempos[key])
        for stage in course.stages[:p.cursor[2]]
        if stage.variant.notes == current_notes
        if (key := stage_key(course.exercise, course.hand, stage.variant,
                            course.profile, course.course_version)) in p.transferable_tempos
        and key in tempos
    ]
    if not earned:
        return None
    return max(SETTINGS.minimum_bpm, min(p.target_bpm,
        round(course.stage.ladder_bpm(max(earned)))))


def stage_start_bpm(course):
    return min(course.progress.target_bpm,
               max(start_bpm(course), minimum_bpm(course), carried_bpm(course) or 0))


def tempo_for_stage(course):
    tempos = dict(course.progress.stage_tempos)
    if course.key in tempos:
        return tempos[course.key]
    start = stage_start_bpm(course)
    if course.exercise.kind != "learn":
        return start
    signature = exact_repetition_signature(course.piece, course.stage.variant.phrase,
        course.hand, course.stage.variant.level, minimum_attacks=SETTINGS.repeated_tempo_min_attacks)
    if signature is None:
        return start
    shared = [start]
    for i, h, v, key in steps(course):
        if key == course.key or key not in tempos or key not in course.progress.transferable_tempos:
            continue
        other = course.with_progress(cursor=(i, h, v))
        if other.exercise.kind == "learn" and exact_repetition_signature(course.piece,
                other.stage.variant.phrase, other.hand, other.stage.variant.level,
                minimum_attacks=SETTINGS.repeated_tempo_min_attacks) == signature:
            shared.append(tempos[key])
    return min(course.progress.target_bpm, max(shared))


def tempo_rungs(course):
    start, target = stage_start_bpm(course), course.progress.target_bpm
    return (target,) if start >= target else tuple(sorted(set(
        start + round((target-start)*i/SETTINGS.automatic_tempo_steps)
        for i in range(SETTINGS.automatic_tempo_steps+1))))



def select_cursor(course, cursor, *, same_is_noop=False):
    if same_is_noop and cursor == course.progress.cursor:
        return course
    tempos = dict(course.progress.stage_tempos)
    tempos[course.key] = course.progress.bpm
    chosen = course.with_progress(cursor=cursor, stage_tempos=tuple(sorted(tempos.items())),
                                  streak=0, failures=0)
    return chosen.with_progress(bpm=tempo_for_stage(chosen))


def manual_progress(course, action, *, number=None, hand=None, bpm=None):
    p = course.progress
    if action in ("select_step", "next", "previous", "select", "hand"):
        if action == "select_step":
            options = steps(course)
            if type(number) is not int or not 1 <= number <= len(options):
                raise ValueError("Lesson step out of bounds")
            destination = options[number-1][:3]
            return select_cursor(course, destination, same_is_noop=True)
        if action == "hand":
            if hand not in course.hands:
                raise ValueError(f"Hand {hand!r} unavailable")
            cursor = (p.cursor[0], course.hands.index(hand), 0)
        else:
            index = number if action == "select" else min(len(course.definition.exercises)-1,
                max(0, p.cursor[0] + (1 if action == "next" else -1)))
            if type(index) is not int or not 0 <= index < len(course.definition.exercises):
                raise ValueError("Exercise index out of bounds")
            cursor = (index, 0, 0)
        return select_cursor(course, cursor)
    if action == "tempo":
        lower = 1
        if type(bpm) not in (int, float) or not math.isfinite(bpm) or not lower <= bpm <= SETTINGS.maximum_bpm:
            raise ValueError(f"BPM must be between {SETTINGS.minimum_bpm} and {SETTINGS.maximum_bpm}")
        target = course.piece.bpm if course.profile == "practice-flow" else bpm
        return course.with_progress(bpm=min(bpm,target), target_bpm=target, stage_tempos=(),
                                    transferable_tempos=(), streak=0, failures=0)
    tempos, transferable = dict(p.stage_tempos), set(p.transferable_tempos)
    if action == "tempo_up" and p.bpm < maximum_bpm(course):
        ceiling = (min(p.target_bpm, maximum_bpm(course))
                   if p.bpm < p.target_bpm else maximum_bpm(course))
        bpm = min(ceiling, p.bpm + SETTINGS.manual_tempo_step_bpm)
        transferable.add(course.key)
    elif action == "tempo_down" and p.bpm > minimum_bpm(course):
        bpm = max(minimum_bpm(course), p.bpm - SETTINGS.manual_tempo_step_bpm)
        if bpm <= stage_start_bpm(course):
            transferable.discard(course.key)
    else:
        return course
    tempos[course.key] = bpm
    return course.with_progress(bpm=bpm, streak=0, failures=0,
        stage_tempos=tuple(sorted(tempos.items())), transferable_tempos=tuple(sorted(transferable)))


def preserve_mastered(course, definition):
    if not course.progress.mastered:
        return definition
    previous = {ex.key: ex for ex in course.definition.exercises}
    sequences = dict(definition.stage_sequences)
    changed = False
    for ex in definition.exercises:
        if previous.get(ex.key) != ex:
            continue
        for hand in lesson_hands(ex):
            old = course.definition.stage_sequences.get((ex.key, hand), ())
            retained = tuple(stage for stage in old if stage_key(ex, hand, stage.variant,
                course.profile, course.course_version) in dict(course.progress.mastered))
            if not retained:
                continue
            selected = sequences[(ex.key, hand)]
            levels = {stage.variant.level for stage in retained}
            terminal = next((stage for stage in retained if stage.variant.level == "original"), selected[-1])
            merged = (*(stage for stage in retained if stage.variant.level != "original"),
                      *(stage for stage in selected[:-1] if stage.variant.level not in levels), terminal)
            if merged != selected:
                sequences[(ex.key, hand)] = merged
                changed = True
    return replace(definition, stage_sequences=sequences) if changed else definition

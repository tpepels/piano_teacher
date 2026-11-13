"""Pure course progression over immutable source definitions and progress.

These are the course algorithms, shared by generator authority and the public
plan API. No operation constructs or mutates a LearningPlan.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import hashlib
import json
import math
from .lesson_generators import LessonPlanDefinition, lesson_hands
from .lesson_settings import SETTINGS
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


@dataclass(frozen=True, slots=True)
class CourseState:
    piece: Piece
    definition: LessonPlanDefinition
    progress: PlanProgress
    profile: str
    course_version: int
    warmup: bool = False

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
    def stages(self):
        return self.definition.stages(self.exercise, self.hand)

    @property
    def stage(self):
        return self.stages[self.progress.cursor[2]]

    @property
    def key(self):
        return stage_key(self.exercise, self.hand, self.stage.variant,
                         self.profile, self.course_version, self.warmup)

    def with_progress(self, **changes):
        return replace(self, progress=replace(self.progress, **changes))


def stage_key(exercise, hand, variant, profile, version, warmup=False):
    phrase = variant.phrase
    events = [(n.start-phrase.start, n.end-phrase.start, n.pitch, n.track, n.channel, n.hand)
              for n in phrase.notes]
    signature = hashlib.sha256(json.dumps((phrase.end-phrase.start, events),
        separators=(",", ":")).encode()).hexdigest()[:16]
    profile = ":warmup" if warmup else f":{profile}"
    return f"course:{version}{profile}:{exercise.key}:{hand}:{variant.level}:{signature}"


def steps(course):
    return tuple((i, h, v, stage_key(ex, hand, stage.variant, course.profile,
                 course.course_version, course.warmup))
                 for i, ex in enumerate(course.definition.exercises)
                 for h, hand in enumerate(lesson_hands(ex))
                 for v, stage in enumerate(course.definition.stages(ex, hand)))


def start_bpm(course):
    p = course.progress
    if course.warmup:
        return min(p.target_bpm, course.piece.bpm)
    baseline = min(p.target_bpm, max(SETTINGS.minimum_bpm, SETTINGS.start_tempo_bpm))
    return min(p.target_bpm, suggested_start_bpm(course.stage.variant.phrase, course.hand,
        default_bpm=baseline, minimum_bpm=SETTINGS.minimum_bpm))


def minimum_bpm(course):
    floor = math.ceil(course.stage.ladder_bpm(SETTINGS.minimum_bpm)-1e-9)
    return max(SETTINGS.minimum_bpm, min(course.progress.target_bpm, floor))


def carried_bpm(course):
    if course.warmup:
        return None
    p = course.progress
    tempos = dict(p.stage_tempos)
    earned = [stage.effective_bpm(tempos[key]) for stage in course.stages[:p.cursor[2]]
              if (key := stage_key(course.exercise, course.hand, stage.variant, course.profile,
                                   course.course_version, course.warmup)) in p.transferable_tempos
              and key in tempos]
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


def next_bpm(course):
    p, rungs = course.progress, tempo_rungs(course)
    if p.bpm < rungs[0]:
        return min(rungs[0], p.bpm + max(SETTINGS.minimum_tempo_step_bpm,
            round((p.target_bpm-rungs[0])/SETTINGS.automatic_tempo_steps)))
    return next((bpm for bpm in rungs if bpm > p.bpm), p.target_bpm)


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
            return select_cursor(course, options[number-1][:3], same_is_noop=True)
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
        if type(bpm) not in (int, float) or not math.isfinite(bpm) or not SETTINGS.minimum_bpm <= bpm <= SETTINGS.maximum_bpm:
            raise ValueError(f"BPM must be between {SETTINGS.minimum_bpm} and {SETTINGS.maximum_bpm}")
        return course.with_progress(bpm=bpm, target_bpm=bpm, stage_tempos=(),
                                    transferable_tempos=(), streak=0, failures=0)
    tempos, transferable = dict(p.stage_tempos), set(p.transferable_tempos)
    if action == "tempo_up" and p.bpm < SETTINGS.maximum_bpm:
        ceiling = p.target_bpm if p.bpm < p.target_bpm else SETTINGS.maximum_bpm
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


def assessed_progress(course, *, correct, total, extras=0, accepted=None, selected_bpm=None):
    p = course.progress
    if total <= 0:
        return course, "No notes to assess"
    accepted = correct == total and extras == 0 if accepted is None else accepted
    if not accepted:
        return course.with_progress(streak=0, failures=p.failures+1), f"Repeat - {correct}/{total} correct, {extras} extra"
    transferable = tuple(sorted(set(p.transferable_tempos) | {course.key}))
    if p.bpm < p.target_bpm:
        bpm = next_bpm(course) if selected_bpm is None else selected_bpm
        tempos = dict(p.stage_tempos)
        tempos[course.key] = bpm
        return course.with_progress(bpm=bpm, streak=0, failures=0,
            stage_tempos=tuple(sorted(tempos.items())), transferable_tempos=transferable), f"Tempo increased to {bpm} BPM"
    course = course.with_progress(failures=0, streak=p.streak+1, transferable_tempos=transferable)
    if course.progress.streak < SETTINGS.clean_runs_to_master:
        label = "Clean" if correct == total and extras == 0 else "Accepted"
        return course, f"{label} pass {course.progress.streak}/{SETTINGS.clean_runs_to_master} - repeat"
    previous = course.key
    tempos, mastered = dict(p.stage_tempos), dict(p.mastered)
    tempos[previous], mastered[previous] = p.bpm, p.target_bpm
    course = course.with_progress(streak=0, stage_tempos=tuple(sorted(tempos.items())),
                                  mastered=tuple(sorted(mastered.items())))
    i, h, v = p.cursor
    if v+1 < len(course.stages):
        course = course.with_progress(cursor=(i, h, v+1))
        course = course.with_progress(bpm=max(tempo_for_stage(course), carried_bpm(course) or SETTINGS.minimum_bpm))
        return course, f"Mastered {previous}; introducing {course.stage.variant.level}"
    if h+1 < len(course.hands):
        course = course.with_progress(cursor=(i, h+1, 0))
        return course.with_progress(bpm=tempo_for_stage(course)), f"Mastered {previous}; now {course.hand} hand"
    if i+1 < len(course.definition.exercises):
        return select_cursor(course, (i+1, 0, 0)), f"Mastered {previous}; next passage"
    return course, "Piece mastered"


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
                course.profile, course.course_version, course.warmup) in dict(course.progress.mastered))
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


def refresh_course(course, definition, *, focus_ids=frozenset()):
    definition = preserve_mastered(course, definition)
    updated = replace(course, definition=definition)
    ex, hand, level = course.exercise, course.hand, course.stage.variant.level
    candidate = None
    if focus_ids and level == "original":
        matching = [(i, item) for i, item in enumerate(definition.exercises)
                    if item.kind == "learn" and any(n.source_id in focus_ids for n in item.phrase.notes)]
        candidate = next(((i, item) for i, item in matching if item.key == ex.key),
                         matching[0] if matching else None)
    if candidate is not None:
        i, target = candidate
        hands = lesson_hands(target)
        updated = updated.with_progress(cursor=(i, hands.index(hand) if hand in hands else 0, 0), streak=0, failures=0)
        return updated.with_progress(bpm=tempo_for_stage(updated))
    retained = next((step for step in steps(updated) if step[3] == course.key), None)
    if retained:
        return updated.with_progress(cursor=retained[:3])
    nearby = next(((i, item) for i, item in enumerate(definition.exercises) if item.key == ex.key), None)
    if nearby is None:
        nearby = next(((i, item) for i, item in enumerate(definition.exercises)
            if item.kind == ex.kind and item.phrase.first_bar >= course.stage.variant.phrase.first_bar),
            (len(definition.exercises)-1, definition.exercises[-1]))
    i, target = nearby
    hands = lesson_hands(target)
    h = hands.index(hand) if hand in hands else 0
    stages = definition.stages(target, hands[h])
    v = next((v for v, stage in enumerate(stages) if stage.variant.level == level),
             len(stages)-1 if level == "original" else 0)
    updated = updated.with_progress(cursor=(i, h, v), streak=0, failures=0)
    return updated.with_progress(bpm=tempo_for_stage(updated))


def revisit_course(course, ids):
    if not ids or course.stage.variant.level != "original":
        return course
    target = next(((i, ex) for i, ex in enumerate(course.definition.exercises)
        if ex.kind == "learn" and any(n.source_id in ids for n in ex.phrase.notes)
        and any(len(course.definition.stages(ex, hand)) > 1 for hand in lesson_hands(ex))), None)
    if target is None:
        return course
    i, ex = target
    error_hands = {n.hand for n in ex.phrase.notes if n.source_id in ids}
    available = lesson_hands(ex)
    hand = next((h for h in (course.hand, "right", "left", "both") if h in available
        and (h == "both" or h in error_hands) and len(course.definition.stages(ex, h)) > 1), None)
    if hand is None:
        return course
    updated = course.with_progress(cursor=(i, available.index(hand), 0), streak=0, failures=0)
    return updated.with_progress(bpm=tempo_for_stage(updated))

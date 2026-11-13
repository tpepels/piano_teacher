"""A compact course with variable focus length for sparse musical material."""
from __future__ import annotations
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, replace
from typing import Mapping
import hashlib
import json
import math
from .exercise_strategies import WARMUP_STRATEGY, resolve_strategy
from .exercise_pipeline import ExerciseStage
from .music import Phrase, Piece
from .exercise_generator import ExerciseVariant
from .musical_groups import grouping_for_piece, MusicalGrouping
from .lesson_settings import SETTINGS
from . import teaching_course as course_policy
from .tempo_difficulty import suggested_start_bpm
from .repeated_passages import exact_repetition_signature
from .lesson_generators import (
    Exercise, LessonGenerator, LessonPlanDefinition, build_lesson_generator,
    lesson_generator_registration,
    lesson_hands,
)

@dataclass(frozen=True)
class LessonStep:
    """One teachable stage; three accepted full-target passes earn mastery."""
    exercise_index: int
    hand: str
    level: str
    key: str
    first_bar: int
    last_bar: int
    required_notes: int
    kind: str


class LearningPlan:
    """Adaptive, manually navigable practice sequence independent of the GUI."""
    def __init__(self, piece: Piece, *, warmup: bool = False,
                 consolidate: bool = False,
                 exercise_strategy: str | None = None,
                 lesson_generator: LessonGenerator | None = None,
                 fukuda_mistakes: frozenset[str] | None = None,
                 feedback: Mapping[str, str] | None = None) -> None:
        self.piece = piece
        # Warmups have their own fixed route; the selected MIDI strategy
        # applies to imported pieces, not the built-in warmup catalog.
        requested = exercise_strategy if exercise_strategy is not None else WARMUP_STRATEGY
        if warmup:
            requested = WARMUP_STRATEGY
        self.exercise_strategy = resolve_strategy(requested,piece=piece)
        self.generator_registration = lesson_generator_registration(
            self.exercise_strategy.name)
        self.warmup = warmup
        # Full-piece MIDI beam inference constructs and reparses MusicXML
        # for *every source attack*. It is only required by generators
        # explicitly declaring grouped-source pedagogy. MIDI-domain Coda /
        # Fukuda authors derive their own groups from their selected passage;
        # compiling source-wide beams for them blocks startup unnecessarily.
        needs_grouping = bool(
            self.generator_registration is not None
            and self.generator_registration.requires_grouping)
        self.grouping = (grouping_for_piece(piece)
                         if not warmup and needs_grouping else None)
        # Produce a complete, immutable course from the entire MIDI Piece
        # before this stateful player owns navigation and mastery.
        self.lesson_generator = lesson_generator or build_lesson_generator(
            self.exercise_strategy.name, consolidate=consolidate, warmup=warmup,
            grouping=self.grouping, mistakes=fukuda_mistakes,
            feedback=feedback)
        self.lesson_definition = self.lesson_generator.generate(piece)
        self.exercises = self.lesson_definition.exercises
        self.index = 0
        self.hand_index = 0
        self.variant_index = 0
        self._variants_cached: tuple | None = None
        self.streak = 0
        self.failures = 0
        self.target_bpm = piece.bpm
        self.mastered: dict[str, int] = {}
        # Tempo is a ladder for each source passage/hand/variant, not just
        # the currently displayed take. Returning to an already practised
        # section must not silently discard its earned BPM progress.
        self.stage_tempos: dict[str, int] = {}
        # Only independently earned tempo advances (clean practice or
        # explicit +BPM), never a settings-target change, are transferable.
        self.transferable_tempos: set[str] = set()
        self._repeated_groups: tuple[dict[str, tuple], dict[tuple, list[str]]] | None = None
        self._lesson_steps_cache: tuple[LessonStep, ...] | None = None
        self._lesson_step_numbers: dict[str, int] = {}
        self.bpm = self.target_bpm
        self.bpm = self.stage_start_bpm

    def capture_teaching_state(self):
        return {key: value.copy() if isinstance(value, (dict, list, set)) else value
                for key, value in vars(self).items()}

    def restore_teaching_state(self, state):
        vars(self).clear()
        vars(self).update(state)

    def teaching_progress(self) -> course_policy.PlanProgress:
        return course_policy.PlanProgress(
            (self.index, self.hand_index, self.variant_index), self.bpm, self.target_bpm,
            self.streak, self.failures, tuple(sorted(self.mastered.items())),
            tuple(sorted(self.stage_tempos.items())), tuple(sorted(self.transferable_tempos)))

    def course_state(self) -> course_policy.CourseState:
        return course_policy.CourseState(self.piece, self.lesson_definition,
            self.teaching_progress(), self.profile,
            self.generator_registration.course_version if self.generator_registration else self.route_version,
            self.warmup)

    def apply_teaching_progress(self, progress, *, definition, expected) -> None:
        """Install an already validated decision, without any policy invocation."""
        if self.teaching_progress() != expected:
            raise ValueError("Teaching progress changed before installation")
        if definition is not self.lesson_definition:
            self._install_definition(definition)
        self.index, self.hand_index, self.variant_index = progress.cursor
        self.bpm, self.target_bpm = progress.bpm, progress.target_bpm
        self.streak, self.failures = progress.streak, progress.failures
        self.mastered = dict(progress.mastered)
        self.stage_tempos = dict(progress.stage_tempos)
        self.transferable_tempos = set(progress.transferable_tempos)
        self._variants_cached = None

    def _install_course(self, course) -> None:
        self.apply_teaching_progress(course.progress, definition=course.definition,
                                     expected=self.teaching_progress())

    route_version = 3

    @property
    def profile(self) -> str:
        return self.lesson_generator.name

    @property
    def start_bpm(self) -> int:
        return course_policy.start_bpm(self.course_state())

    @property
    def minimum_stage_bpm(self) -> int:
        return course_policy.minimum_bpm(self.course_state())

    def carried_bpm(self) -> int | None:
        return course_policy.carried_bpm(self.course_state())

    @property
    def stage_start_bpm(self) -> int:
        return course_policy.stage_start_bpm(self.course_state())

    @property
    def exercise(self) -> Exercise:
        return self.exercises[self.index]

    @property
    def hands(self) -> tuple[str, ...]:
        return lesson_hands(self.exercise)

    @property
    def hand(self) -> str:
        return self.hands[self.hand_index]

    @property
    def stages(self) -> tuple[ExerciseStage, ...]:
        key = (self.index, self.hand)
        if self._variants_cached is None or self._variants_cached[0] != key:
            self._variants_cached = (key, self._pipeline_stages(self.exercise, self.hand))
        return self._variants_cached[1]

    @property
    def variants(self) -> tuple[ExerciseVariant, ...]:
        return tuple(stage.variant for stage in self.stages)

    @property
    def accepts_performance_feedback(self) -> bool:
        """Generators opt in through a common immutable feedback hook."""
        return callable(getattr(self.lesson_generator, "with_feedback", None))

    def feedback_changes_generator(self, evidence: Mapping[str, str]) -> bool:
        """Whether refresh_from_feedback(evidence) would rebuild the course.

        Only the immutable feedback hook runs (microseconds); the rebuild
        itself is left to refresh_from_feedback.
        """
        hook = getattr(self.lesson_generator, "with_feedback", None)
        return callable(hook) and hook(
            evidence, self.lesson_definition) is not self.lesson_generator

    def refresh_from_feedback(
        self, evidence: Mapping[str, str], *, prefer_repair: bool = True,
        focus_ids: frozenset[str] | None = None,
    ) -> bool:
        """Rebuild selected stages from actual original-attack error families."""
        if not isinstance(evidence, Mapping) or any(
                not isinstance(k, str) or not isinstance(v, str)
                for k, v in evidence.items()):
            raise TypeError("Generator needs source-identified MIDI feedback")
        if focus_ids is not None and (
                not isinstance(focus_ids, frozenset)
                or not focus_ids <= evidence.keys()):
            raise ValueError("Focus must identify currently failed source attacks")
        # Previously stored errors may belong to another passage. Never
        # relocate the learner for old evidence during a new assessment.
        target_ids = ((frozenset(evidence) if focus_ids is None else focus_ids)
                      if prefer_repair else frozenset())
        hook = getattr(self.lesson_generator, "with_feedback", None)
        if callable(hook):
            updated = hook(evidence, self.lesson_definition)
            return self._refresh_generator(updated, focus_ids=target_ids)
        return False

    def _refresh_generator(
        self, updated: LessonGenerator, *, focus_ids: frozenset[str],
    ) -> bool:
        if updated is self.lesson_generator:
            return False
        course = course_policy.refresh_course(self.course_state(), updated.generate(self.piece), focus_ids=focus_ids)
        self._install_course(course)
        self.lesson_generator = updated
        return True

    def _preserve_mastered_stages(
        self, definition: LessonPlanDefinition, previous: LessonPlanDefinition,
        keys: Mapping[str, int],
    ) -> LessonPlanDefinition:
        course = replace(self.course_state(), definition=previous,
                         progress=replace(self.teaching_progress(), mastered=tuple(sorted(keys.items()))))
        return course_policy.preserve_mastered(course, definition)

    def _install_definition(self, definition: LessonPlanDefinition) -> None:
        self.lesson_definition = definition
        self.exercises = definition.exercises
        self._variants_cached = None
        self._lesson_steps_cache = None
        self._lesson_step_numbers = {}
        self._repeated_groups = None

    def restore_mastered_stages(self, keys: Mapping[str, int]) -> None:
        """Recover only exact current-course identities from its source catalog."""
        catalog = getattr(self.lesson_generator, "catalog", None)
        if not isinstance(catalog, LessonPlanDefinition):
            return
        definition = self._preserve_mastered_stages(self.lesson_definition, catalog, keys)
        if definition is not self.lesson_definition:
            level = self.active_variant.level
            self._install_definition(definition)
            self.variant_index = next(i for i, stage in enumerate(self.stages)
                                      if stage.variant.level == level)

    def revisit_source_errors(self, ids: frozenset[str]) -> bool:
        before = self.course_state()
        chosen = course_policy.revisit_course(before, ids)
        if chosen is before:
            return False
        self._install_course(chosen)
        return True

    def _pipeline_stages(self, exercise: Exercise, hand: str) -> tuple[ExerciseStage, ...]:
        """Read the generated course; never choose passages on navigation."""
        return self.lesson_definition.stages(exercise,hand)

    def _stage_variants(self, exercise: Exercise, hand: str) -> tuple[ExerciseVariant, ...]:
        return tuple(stage.variant for stage in self.lesson_definition.stages(exercise,hand))

    def _stage_key(self, exercise: Exercise, hand: str, variant: ExerciseVariant) -> str:
        version = self.generator_registration.course_version if self.generator_registration is not None else self.route_version
        return course_policy.stage_key(exercise, hand, variant, self.profile, version, self.warmup)

    @property
    def lesson_steps(self) -> tuple[LessonStep, ...]:
        """Build once; progress is across hands and levels, not MIDI measures."""
        if self._lesson_steps_cache is None:
            steps: list[LessonStep] = []
            for index, ex in enumerate(self.exercises):
                hands = lesson_hands(ex)
                for hand in hands:
                    for variant in self._stage_variants(ex, hand):
                        steps.append(LessonStep(
                            index, hand, variant.level, self._stage_key(ex, hand, variant),
                            ex.phrase.first_bar, ex.phrase.last_bar,
                            len(variant.notes), ex.kind))
            self._lesson_steps_cache = tuple(steps)
            self._lesson_step_numbers = {
                step.key: index for index, step in enumerate(steps, start=1)}
        return self._lesson_steps_cache

    @property
    def lesson_step_number(self) -> int:
        # The UI queries the current cursor every 20ms. Its stable stage key
        # already identifies the selected lesson; avoid scanning thousands
        # of immutable Hanon course stages for each state snapshot.
        self.lesson_steps
        return self._lesson_step_numbers.get(self.identity, 1)

    @property
    def lesson_steps_mastered(self) -> int:
        self.lesson_steps
        return sum(key in self._lesson_step_numbers for key in self.mastered)

    @property
    def active_stage(self) -> ExerciseStage:
        return self.stages[self.variant_index]

    @property
    def active_variant(self) -> ExerciseVariant:
        return self.active_stage.variant

    @property
    def active_phrase(self) -> Phrase:
        return self.active_variant.phrase

    @property
    def identity(self) -> str:
        return self._stage_key(self.exercise, self.hand, self.active_variant)

    def _tempo_for_current_stage(self) -> int:
        # A stage with its own local history keeps its own BPM, including
        # failure-driven slowdowns. Only genuinely UNSEEN repeated passages
        # may inherit a higher starting tempo from already visited stages.
        return course_policy.tempo_for_stage(self.course_state())

    def restore_location(self, *, kind: str, first_bar: int, last_bar: int,
                         hand: str, level: str) -> None:
        """Find saved source material in this course without reusing a stale index."""
        candidates = [(i, ex) for i, ex in enumerate(self.exercises)
                      if ex.phrase.first_bar <= first_bar and ex.phrase.last_bar >= last_bar]
        preferred = [(i, ex) for i, ex in candidates if ex.kind == kind]
        if not preferred and kind == "learn":
            # A previously saved whole-score Coda learn (1..73) must not
            # silently reopen as the final full-piece performance after
            # switching the desktop course to bounded teaching passages.
            # Preserve the starting source measure and seek within the
            # new learning route, even when the old interval no longer fits.
            preferred = [(i, ex) for i, ex in enumerate(self.exercises)
                         if ex.kind == "learn"
                         and ex.phrase.first_bar <= first_bar <= ex.phrase.last_bar]
            if not preferred:
                following = [(i, ex) for i, ex in enumerate(self.exercises)
                             if ex.kind == "learn" and ex.phrase.first_bar >= first_bar]
                if following:
                    closest_bar = min(ex.phrase.first_bar for _, ex in following)
                    preferred = [(i, ex) for i, ex in following
                                 if ex.phrase.first_bar == closest_bar]
        if not preferred:
            preferred = [(i, ex) for i, ex in candidates if ex.kind == "learn"]
        if not preferred and not candidates:
            # Migration from the old 8-bar route: resume at the focused
            # unit containing the old lesson's first source measure.
            preferred = [(i,ex) for i,ex in enumerate(self.exercises)
                         if ex.kind == "learn"
                         and ex.phrase.first_bar <= first_bar <= ex.phrase.last_bar]
        if preferred or candidates:
            self.select(min(preferred or candidates,
                            key=lambda pair: pair[1].phrase.last_bar - pair[1].phrase.first_bar)[0])
        if hand in self.hands:
            self.set_hand(hand)
        self.variant_index = next((i for i, variant in enumerate(self.variants) if variant.level == level), 0)
        self.bpm = self._tempo_for_current_stage()

    def jump(self, amount: int) -> None:
        self.select(min(len(self.exercises) - 1, max(0, self.index + amount)))

    def select_step(self, number: int) -> None:
        self._install_course(course_policy.manual_progress(self.course_state(), "select_step", number=number))

    def select(self, index: int) -> None:
        self._install_course(course_policy.manual_progress(self.course_state(), "select", number=index))

    def set_hand(self, hand: str) -> None:
        self._install_course(course_policy.manual_progress(self.course_state(), "hand", hand=hand))

    def set_bpm(self, bpm: int) -> None:
        self._install_course(course_policy.manual_progress(self.course_state(), "tempo", bpm=bpm))

    def tempo_rungs(self) -> tuple[int, ...]:
        return course_policy.tempo_rungs(self.course_state())

    def _next_automatic_bpm(self) -> int:
        return course_policy.next_bpm(self.course_state())

    def decrease_tempo(self) -> int:
        self._install_course(course_policy.manual_progress(self.course_state(), "tempo_down"))
        return self.bpm

    def increase_tempo(self) -> int:
        self._install_course(course_policy.manual_progress(self.course_state(), "tempo_up"))
        return self.bpm

    def bpm_after(self, accepted: bool) -> float:
        return course_policy.next_bpm(self.course_state()) if accepted and self.bpm < self.target_bpm else self.bpm

    def apply_result(self, *, correct: int, total: int, extras: int = 0,
                     accepted: bool | None = None,
                     next_bpm: float | None = None) -> str:
        course, message = course_policy.assessed_progress(self.course_state(), correct=correct,
            total=total, extras=extras, accepted=accepted, selected_bpm=next_bpm)
        self._install_course(course)
        return message

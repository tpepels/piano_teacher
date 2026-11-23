"""A compact course with variable focus length for sparse musical material."""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Mapping
from .exercise_pipeline import ExerciseStage
from .music import Phrase, Piece
from .exercise_generator import ExerciseVariant
from . import teaching_course as course_policy
from .lesson_contracts import Exercise, LessonGenerator, LessonPlanDefinition, lesson_hands
from .practice_flow_course import PracticeFlowLessonGenerator, COURSE_VERSION

@dataclass(frozen=True)
class LessonStep:
    """One teachable stage; mastery count comes from its selected course."""
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
    def __init__(self, piece: Piece, *,
                 lesson_generator: LessonGenerator | None = None) -> None:
        if piece.source_format != "midi":
            raise ValueError("Practice Flow requires an imported MIDI piece")
        self.piece = piece
        # Produce a complete, immutable course from the entire MIDI Piece
        # before this stateful player owns navigation and mastery.
        self.lesson_generator = lesson_generator or PracticeFlowLessonGenerator()
        self.lesson_definition = self.lesson_generator.generate(piece)
        self.exercises = self.lesson_definition.exercises
        self.index = 0
        self.hand_index = 0
        self.variant_index = 0
        self._variants_cached: tuple | None = None
        self.streak = 0
        self.failures = 0
        self.free_returns: dict[str,int] = {}
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
            tuple(sorted(self.stage_tempos.items())), tuple(sorted(self.transferable_tempos)),
            tuple(sorted(self.free_returns.items())))

    def course_state(self) -> course_policy.CourseState:
        return course_policy.CourseState(self.piece, self.lesson_definition,
            self.teaching_progress(), self.profile, COURSE_VERSION)

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
        self.free_returns = dict(progress.free_returns)
        self._variants_cached = None

    def _install_course(self, course) -> None:
        self.apply_teaching_progress(course.progress, definition=course.definition,
                                     expected=self.teaching_progress())

    # Stored with saved sessions and evidence; kept for their schema.
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

    @property
    def maximum_stage_bpm(self) -> int:
        return course_policy.maximum_bpm(self.course_state())

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

    def _pipeline_stages(self, exercise: Exercise, hand: str) -> tuple[ExerciseStage, ...]:
        """Read the generated course; never choose passages on navigation."""
        return self.lesson_definition.stages(exercise,hand)

    def stage_variants(self, exercise: Exercise, hand: str) -> tuple[ExerciseVariant, ...]:
        return tuple(stage.variant for stage in self.lesson_definition.stages(exercise,hand))

    def _stage_key(self, exercise: Exercise, hand: str, variant: ExerciseVariant) -> str:
        return course_policy.stage_key(exercise, hand, variant, self.profile, COURSE_VERSION)

    @property
    def lesson_steps(self) -> tuple[LessonStep, ...]:
        """Build once; progress is across hands and levels, not MIDI measures."""
        if self._lesson_steps_cache is None:
            steps: list[LessonStep] = []
            for index, ex in enumerate(self.exercises):
                hands = lesson_hands(ex)
                for hand in hands:
                    for variant in self.stage_variants(ex, hand):
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

    def select(self, index: int) -> None:
        self._install_course(course_policy.manual_progress(self.course_state(), "select", number=index))

    def set_hand(self, hand: str) -> None:
        self._install_course(course_policy.manual_progress(self.course_state(), "hand", hand=hand))

    def tempo_rungs(self) -> tuple[int, ...]:
        return course_policy.tempo_rungs(self.course_state())

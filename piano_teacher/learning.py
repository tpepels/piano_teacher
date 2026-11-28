"""The installed Practice Flow course of one piece: its step list and cursor.

LearningPlan holds the mutable progress of teaching_course's pure model and
exposes the current step's source (window, hand, notes) to the application.
Only a validated teaching decision changes it (apply_teaching_progress).
"""
from __future__ import annotations
from .exercise_pipeline import ExerciseStage
from .music import Phrase, Piece
from .exercise_generator import ExerciseVariant
from . import teaching_course as course_policy
from .lesson_contracts import Exercise, LessonGenerator, lesson_hands
from .practice_flow_course import PracticeFlowLessonGenerator, COURSE_VERSION

LessonStep = course_policy.Step


class LearningPlan:
    def __init__(self, piece: Piece, *,
                 lesson_generator: LessonGenerator | None = None) -> None:
        if piece.source_format not in ("midi", "musicxml"):
            raise ValueError("Practice Flow requires an imported piece")
        self.piece = piece
        self.lesson_generator = lesson_generator or PracticeFlowLessonGenerator()
        self.lesson_definition = self.lesson_generator.generate(piece)
        self.exercises = self.lesson_definition.exercises
        self.position = 0
        self.target_bpm = piece.bpm
        self.bpm = piece.bpm
        self.streak = 0
        self.failures = 0
        self.mastered: dict[str, int] = {}
        self.free_returns: dict[str, int] = {}

    # Stored with saved sessions and evidence; kept for their schema.
    route_version = 3
    # The (removed) per-window variant dimension; saved rows still carry it.
    variant_index = 0

    def capture_teaching_state(self):
        return {key: value.copy() if isinstance(value, (dict, list, set)) else value
                for key, value in vars(self).items()}

    def restore_teaching_state(self, state):
        vars(self).clear()
        vars(self).update(state)

    def teaching_progress(self) -> course_policy.PlanProgress:
        return course_policy.PlanProgress(
            self.position, self.bpm, self.target_bpm, self.streak, self.failures,
            tuple(sorted(self.mastered.items())), tuple(sorted(self.free_returns.items())))

    def course_state(self) -> course_policy.CourseState:
        return course_policy.CourseState(self.piece, self.lesson_definition,
            self.teaching_progress(), self.profile, COURSE_VERSION)

    def apply_teaching_progress(self, progress, *, definition, expected) -> None:
        """Install an already validated decision, without any policy invocation."""
        if self.teaching_progress() != expected:
            raise ValueError("Teaching progress changed before installation")
        if definition is not self.lesson_definition:
            raise ValueError("A teaching decision cannot replace the course")
        self.position = progress.position
        self.bpm, self.target_bpm = progress.bpm, progress.target_bpm
        self.streak, self.failures = progress.streak, progress.failures
        self.mastered = dict(progress.mastered)
        self.free_returns = dict(progress.free_returns)

    def _install_course(self, course) -> None:
        self.apply_teaching_progress(course.progress, definition=course.definition,
                                     expected=self.teaching_progress())

    @property
    def profile(self) -> str:
        return self.lesson_generator.name

    # --- The step list ---------------------------------------------------

    @property
    def lesson_steps(self) -> tuple[LessonStep, ...]:
        return course_policy.course_steps(self.lesson_definition, self.profile, COURSE_VERSION)

    @property
    def step(self) -> LessonStep:
        return self.lesson_steps[self.position]

    @property
    def lesson_step_number(self) -> int:
        return self.position+1

    @property
    def lesson_steps_mastered(self) -> int:
        return sum(step.key in self.mastered for step in self.lesson_steps)

    @property
    def index(self) -> int:
        return self.step.exercise_index

    @property
    def exercise(self) -> Exercise:
        return self.exercises[self.index]

    @property
    def hands(self) -> tuple[str, ...]:
        return lesson_hands(self.exercise)

    @property
    def hand(self) -> str:
        return self.step.hand

    @property
    def stages(self) -> tuple[ExerciseStage, ...]:
        return self.lesson_definition.stages(self.exercise, self.hand)

    @property
    def variants(self) -> tuple[ExerciseVariant, ...]:
        return tuple(stage.variant for stage in self.stages)

    @property
    def active_stage(self) -> ExerciseStage:
        return self.stages[0]

    @property
    def active_variant(self) -> ExerciseVariant:
        return self.active_stage.variant

    @property
    def active_phrase(self) -> Phrase:
        return self.active_variant.phrase

    @property
    def identity(self) -> str:
        return self.step.key

    # --- Tempo bounds (Practice Flow: 50% of target .. target) -----------

    @property
    def minimum_stage_bpm(self) -> int:
        return course_policy.floor_bpm(self.course_state())

    @property
    def maximum_stage_bpm(self) -> int:
        return int(self.target_bpm)

    stage_start_bpm = minimum_stage_bpm

    def tempo_rungs(self) -> tuple[int, ...]:
        from .application.practice_flow import step_bpm
        floor, target = self.minimum_stage_bpm, int(self.target_bpm)
        return tuple(range(floor, target, max(1, step_bpm(target)))) + (target,)

    # --- Navigation used when opening/restoring --------------------------

    def restore_position(self, key: str | None = None, *, first_bar: int | None = None,
                         hand: str | None = None) -> bool:
        """Place the cursor on a saved step key, else on the single-measure
        window of a saved first bar (and hand). Returns True for an exact key."""
        steps = self.lesson_steps
        for index, step in enumerate(steps):
            if step.key == key:
                self.position = index
                return True
        if first_bar is not None:
            candidates = [i for i, s in enumerate(steps) if s.kind == "learn"
                          and s.first_bar <= first_bar <= s.last_bar]
            if candidates:
                best = min(candidates, key=lambda i: (steps[i].last_bar-steps[i].first_bar,
                                                      steps[i].hand != hand))
                self.position = best
        return False

    def select(self, index: int) -> None:
        self._install_course(course_policy.manual_progress(self.course_state(), "select", number=index))

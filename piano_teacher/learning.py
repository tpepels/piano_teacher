"""Deterministic two-bar learning and overlapping four-bar connections."""
from __future__ import annotations
from dataclasses import dataclass
from .music import Phrase, Piece
from .exercise_generator import ExerciseVariant, generate_variants

@dataclass(frozen=True)
class Exercise:
    kind: str
    phrase: Phrase
    key: str


def build_exercises(piece: Piece) -> tuple[Exercise, ...]:
    """Learn A, learn B, connect A+B; learn C, connect B+C, ..."""
    phrases = piece.phrases
    exercises: list[Exercise] = []
    for index, phrase in enumerate(phrases):
        exercises.append(Exercise("learn", phrase, f"learn:{phrase.first_bar}-{phrase.last_bar}"))
        if index > 0:
            prev = phrases[index - 1]
            # Do not imply continuity if there is a silent/gapped passage.
            if prev.last_bar + 1 == phrase.first_bar:
                joined = Phrase(0, prev.first_bar, phrase.last_bar, prev.start, phrase.end,
                                tuple(n for n in piece.notes if prev.start <= n.start < phrase.end))
                exercises.append(Exercise("connect", joined, f"connect:{joined.first_bar}-{joined.last_bar}"))
    if len(phrases) > 1:
        combined = Phrase(0, phrases[0].first_bar, phrases[-1].last_bar,
                          phrases[0].start, phrases[-1].end,
                          tuple(n for n in piece.notes if phrases[0].start <= n.start < phrases[-1].end))
        exercises.append(Exercise("perform", combined, "perform:all"))
    return tuple(exercises)


@dataclass(frozen=True)
class LessonStep:
    """One teachable stage; three clean target-tempo passes earn mastery."""
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
    def __init__(self, piece: Piece) -> None:
        self.piece = piece
        self.exercises = build_exercises(piece)
        if not self.exercises:
            raise ValueError("Piece has no practice passages")
        self.index = 0
        self.hand_index = 0
        self.variant_index = 0
        self._variants_cached: tuple | None = None
        self.streak = 0
        self.failures = 0
        self.bpm = self.start_bpm
        self.target_bpm = piece.bpm
        self.mastered: dict[str, int] = {}
        self._lesson_steps_cache: tuple[LessonStep, ...] | None = None

    @property
    def start_bpm(self) -> int:
        return max(12, round(self.piece.bpm * 0.4))

    @property
    def exercise(self) -> Exercise:
        return self.exercises[self.index]

    @property
    def hands(self) -> tuple[str, ...]:
        if self.exercise.kind != "learn":
            return ("both",)
        available = {n.hand for n in self.exercise.phrase.notes}
        individual = tuple(h for h in ("right", "left") if h in available)
        return individual + ("both",)

    @property
    def hand(self) -> str:
        return self.hands[self.hand_index]

    @property
    def variants(self) -> tuple[ExerciseVariant, ...]:
        key = (self.index, self.hand)
        if self._variants_cached is None or self._variants_cached[0] != key:
            self._variants_cached = (key, generate_variants(self.exercise.phrase, self.hand))
        return self._variants_cached[1]

    @property
    def lesson_steps(self) -> tuple[LessonStep, ...]:
        """Build once; progress is across hands and levels, not MIDI measures."""
        if self._lesson_steps_cache is None:
            steps: list[LessonStep] = []
            for index, ex in enumerate(self.exercises):
                if ex.kind == "learn":
                    available = {note.hand for note in ex.phrase.notes}
                    hands = tuple(hand for hand in ("right", "left") if hand in available) + ("both",)
                else:
                    hands = ("both",)
                for hand in hands:
                    for variant in generate_variants(ex.phrase, hand):
                        steps.append(LessonStep(
                            index, hand, variant.level, f"{ex.key}:{hand}:{variant.level}",
                            ex.phrase.first_bar, ex.phrase.last_bar,
                            len(variant.notes), ex.kind))
            self._lesson_steps_cache = tuple(steps)
        return self._lesson_steps_cache

    @property
    def lesson_step_number(self) -> int:
        return next((i + 1 for i, step in enumerate(self.lesson_steps)
                     if step.key == self.identity), 1)

    @property
    def lesson_steps_mastered(self) -> int:
        return sum(step.key in self.mastered for step in self.lesson_steps)

    @property
    def active_variant(self) -> ExerciseVariant:
        return self.variants[self.variant_index]

    @property
    def active_phrase(self) -> Phrase:
        return self.active_variant.phrase

    @property
    def identity(self) -> str:
        return f"{self.exercise.key}:{self.hand}:{self.active_variant.level}"

    def jump(self, amount: int) -> None:
        self.select(min(len(self.exercises) - 1, max(0, self.index + amount)))

    def select(self, index: int) -> None:
        if not 0 <= index < len(self.exercises):
            raise ValueError("Exercise index out of bounds")
        self.index = index
        self.hand_index = 0
        self.variant_index = 0
        self.bpm = self.start_bpm
        self.target_bpm = self.piece.bpm
        self.streak = 0
        self.failures = 0

    def set_hand(self, hand: str) -> None:
        if hand not in self.hands:
            raise ValueError(f"Hand {hand!r} unavailable")
        self.hand_index = self.hands.index(hand)
        self.variant_index = 0
        self.streak = self.failures = 0
        self.bpm = self.start_bpm
        self.target_bpm = self.piece.bpm

    def set_bpm(self, bpm: int) -> None:
        if bpm < 12 or bpm > 300:
            raise ValueError("BPM must be between 12 and 300")
        self.bpm = bpm
        self.target_bpm = bpm
        self.streak = self.failures = 0

    def apply_result(self, *, correct: int, total: int, extras: int = 0) -> str:
        """A clean run restores tempo; three target-speed clean runs confer mastery.

        Recovery slowdowns happen on five pitch errors in a two-bar window.
        Partial retries never call this method.
        """
        if total <= 0:
            return "No notes to assess"
        clean = correct == total and extras == 0
        if not clean:
            self.streak = 0
            self.failures += 1
            return f"Repeat - {correct}/{total} correct, {extras} extra"
        self.failures = 0
        if self.bpm < self.target_bpm:
            self.streak = 0
            self.bpm = min(self.target_bpm, max(self.bpm + 1, round(self.bpm * 1.10)))
            return f"Tempo increased to {self.bpm} BPM"
        self.streak += 1
        if self.streak < 3:
            return f"Clean pass {self.streak}/3 - repeat"
        self.streak = 0
        previous = self.identity
        self.mastered[previous] = self.target_bpm
        if self.variant_index + 1 < len(self.variants):
            self.variant_index += 1
            self.bpm = self.start_bpm
            return f"Mastered {previous}; introducing {self.active_variant.level}"
        if self.hand_index + 1 < len(self.hands):
            self.hand_index += 1
            self.variant_index = 0
            self.bpm = self.start_bpm
            return f"Mastered {previous}; now {self.hand} hand"
        if self.index + 1 < len(self.exercises):
            self.select(self.index + 1)
            return f"Mastered {previous}; next passage"
        return "Piece mastered"

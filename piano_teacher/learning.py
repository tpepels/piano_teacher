"""Deterministic two-bar learning and overlapping four-bar connections."""
from __future__ import annotations
from dataclasses import dataclass
from .music import Phrase, Piece

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


class LearningPlan:
    """Adaptive, manually navigable practice sequence independent of the GUI."""
    def __init__(self, piece: Piece) -> None:
        self.piece = piece
        self.exercises = build_exercises(piece)
        if not self.exercises:
            raise ValueError("Piece has no practice passages")
        self.index = 0
        self.hand_index = 0
        self.streak = 0
        self.failures = 0
        self.bpm = self.start_bpm
        self.mastered: dict[str, int] = {}

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
    def identity(self) -> str:
        return f"{self.exercise.key}:{self.hand}"

    def jump(self, amount: int) -> None:
        self.select(min(len(self.exercises) - 1, max(0, self.index + amount)))

    def select(self, index: int) -> None:
        if not 0 <= index < len(self.exercises):
            raise ValueError("Exercise index out of bounds")
        self.index = index
        self.hand_index = 0
        self.bpm = self.start_bpm
        self.streak = 0
        self.failures = 0

    def set_hand(self, hand: str) -> None:
        if hand not in self.hands:
            raise ValueError(f"Hand {hand!r} unavailable")
        self.hand_index = self.hands.index(hand)
        self.streak = self.failures = 0
        self.bpm = self.start_bpm

    def set_bpm(self, bpm: int) -> None:
        if bpm < 12 or bpm > 300:
            raise ValueError("BPM must be between 12 and 300")
        self.bpm = bpm
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
        if self.bpm < self.piece.bpm:
            self.streak = 0
            self.bpm = min(self.piece.bpm, max(self.bpm + 1, round(self.bpm * 1.10)))
            return f"Tempo increased to {self.bpm} BPM"
        self.streak += 1
        if self.streak < 3:
            return f"Clean pass {self.streak}/3 - repeat"
        self.streak = 0
        previous = self.identity
        self.mastered[previous] = self.piece.bpm
        if self.hand_index + 1 < len(self.hands):
            self.hand_index += 1
            self.bpm = self.start_bpm
            return f"Mastered {previous}; now {self.hand} hand"
        if self.index + 1 < len(self.exercises):
            self.select(self.index + 1)
            return f"Mastered {previous}; next passage"
        return "Piece mastered"

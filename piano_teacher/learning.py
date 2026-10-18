"""A compact course with two-bar focus work for difficult musical material."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from .music import Phrase, Piece
from .exercise_generator import ExerciseVariant, generate_variants

@dataclass(frozen=True)
class Exercise:
    kind: str
    phrase: Phrase
    key: str


def _difficult(phrase: Phrase) -> bool:
    """Keep dense chords and fast/irregular figures in their original short unit.

    This is deliberately a bounded first-course heuristic, not a claim to
    infer musical phrases or a player's skill from a MIDI file.
    """
    duration = max(1.0, phrase.end - phrase.start)
    for hand in ("right", "left"):
        notes = [n for n in phrase.notes if n.hand == hand]
        onsets = sorted({round(n.start, 6) for n in notes})
        chords = Counter(round(n.start, 6) for n in notes)
        density = len(notes) / duration
        irregular = sum(abs(n.start * 2 - round(n.start * 2)) > .05 for n in notes)
        # Near-simultaneous MIDI attacks can be rolled chords, not fast
        # separate figures. A substantial run of short intervals is harder.
        quick = sum(.08 < b - a < .25 - 1e-6 for a, b in zip(onsets, onsets[1:]))
        if (density > 3 or max(chords.values(), default=0) > 4 or quick >= max(3, len(onsets) * .25)
                or (density > 1.5 and irregular > len(notes) * .5)):
            return True
    return False


def _course_phrases(piece: Piece) -> tuple[Phrase, ...]:
    groups: list[Phrase] = []
    pending: list[Phrase] = []

    def flush() -> None:
        if pending:
            first, last = pending[0], pending[-1]
            groups.append(Phrase(len(groups) + 1, first.first_bar, last.last_bar,
                                 first.start, last.end, tuple(n for p in pending for n in p.notes)))
            pending.clear()

    for phrase in piece.phrases:
        hard = _difficult(phrase)
        if pending:
            previous = pending[-1]
            crosses_meter = any(pending[0].start < beat <= phrase.start
                                for beat, _, _ in piece.time_signatures)
            if (hard or previous.last_bar + 1 != phrase.first_bar
                    or abs(previous.end - phrase.start) > 1e-6
                    or phrase.last_bar - pending[0].first_bar + 1 > 8 or crosses_meter):
                flush()
        pending.append(phrase)
        if hard:
            flush()
    flush()
    return tuple(groups)


def build_exercises(piece: Piece, *, consolidate: bool = True) -> tuple[Exercise, ...]:
    """Learn sections, bridge their boundaries, then perform the complete source.

    The original two-bar sequence remains reconstructible for old progress.
    """
    phrases = _course_phrases(piece) if consolidate else piece.phrases
    exercises: list[Exercise] = []
    for index, phrase in enumerate(phrases):
        exercises.append(Exercise("learn", phrase, f"learn:{phrase.first_bar}-{phrase.last_bar}"))
        if index > 0:
            prev = phrases[index - 1]
            # Do not imply continuity if there is a silent/gapped passage.
            if prev.last_bar + 1 == phrase.first_bar:
                first_bar = max(prev.first_bar, prev.last_bar - 1) if consolidate else prev.first_bar
                last_bar = min(phrase.last_bar, phrase.first_bar + 1) if consolidate else phrase.last_bar
                # Use source units rather than guessed equal-duration measures.
                source = [p for p in piece.phrases if p.first_bar >= first_bar and p.last_bar <= last_bar]
                start, end = (source[0].start, source[-1].end) if source else (prev.start, phrase.end)
                joined = Phrase(0, first_bar, last_bar, start, end,
                                tuple(n for n in piece.notes if start <= n.start < end))
                exercises.append(Exercise("connect", joined, f"connect:{joined.first_bar}-{joined.last_bar}"))
    if not consolidate and len(phrases) > 1:
        combined = Phrase(0, phrases[0].first_bar, phrases[-1].last_bar,
                          phrases[0].start, phrases[-1].end,
                          tuple(n for n in piece.notes if phrases[0].start <= n.start < phrases[-1].end))
        exercises.append(Exercise("perform", combined, "perform:all"))
        return tuple(exercises)
    last_release = max((n.end for n in piece.notes), default=phrases[-1].end) if phrases else 0.0
    source_end = piece.bar_boundaries[-1] if piece.bar_boundaries else last_release
    source_start = piece.bar_boundaries[0] if piece.bar_boundaries else 0.0
    if phrases and (len(piece.phrases) > 1 or source_start < phrases[0].start - 1e-6
                    or max(last_release, source_end) > phrases[-1].end + 1e-6):
        # Empty-onset measures are omitted from targeted source passages, but
        # the complete performance includes introduction rests and held endings.
        start = piece.bar_boundaries[0] if piece.bar_boundaries else phrases[0].start
        end = max(phrases[-1].end, last_release, piece.bar_boundaries[-1] if piece.bar_boundaries else 0)
        first_bar = 1 if piece.bar_boundaries else phrases[0].first_bar
        if piece.bar_boundaries and piece.bar_boundaries[-1] >= last_release:
            last_bar = len(piece.bar_boundaries) - 1
        else:
            beats_per_bar = (phrases[-1].end - phrases[-1].start) / max(1, phrases[-1].last_bar - phrases[-1].first_bar + 1)
            last_bar = phrases[-1].last_bar + math.ceil(max(0, end - phrases[-1].end) / beats_per_bar)
        combined = Phrase(0, first_bar, last_bar, start, end, piece.notes)
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
    def __init__(self, piece: Piece, *, warmup: bool = False) -> None:
        self.piece = piece
        self.warmup = warmup
        if warmup:
            # Short three-stage course, with full eight-bar phrases.
            duration = piece.bar_boundaries[-1] if piece.bar_boundaries else max(n.end for n in piece.notes)
            bars = len(piece.bar_boundaries) - 1 if piece.bar_boundaries else piece.phrases[-1].last_bar
            self.exercises = (Exercise("warmup", Phrase(0, 1, bars, 0.0, duration, piece.notes), "warmup:all"),)
        else:
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

    route_version = 2

    @property
    def start_bpm(self) -> int:
        if self.warmup:
            return min(getattr(self, "target_bpm", self.piece.bpm), self.piece.bpm)
        return min(getattr(self, "target_bpm", self.piece.bpm), max(12, round(self.piece.bpm * 0.4)))

    @property
    def exercise(self) -> Exercise:
        return self.exercises[self.index]

    @property
    def hands(self) -> tuple[str, ...]:
        if self.warmup:
            return ("right", "left", "both")
        if self.exercise.kind != "learn":
            return ("both",)
        available = {n.hand for n in self.exercise.phrase.notes}
        individual = tuple(h for h in ("right", "left") if h in available)
        return individual + (("both",) if len(individual) > 1 else ())

    @property
    def hand(self) -> str:
        return self.hands[self.hand_index]

    @property
    def variants(self) -> tuple[ExerciseVariant, ...]:
        key = (self.index, self.hand)
        if self._variants_cached is None or self._variants_cached[0] != key:
            self._variants_cached = (key, self._stage_variants(self.exercise, self.hand))
        return self._variants_cached[1]

    @staticmethod
    def _stage_variants(exercise: Exercise, hand: str) -> tuple[ExerciseVariant, ...]:
        variants = generate_variants(exercise.phrase, hand)
        if hand == "both" or exercise.kind != "learn":
            return variants[-1:]
        if len(variants) == 3:
            skeleton, outline, original = variants
            # A nearly identical middle stage adds repetition without a
            # substantial change in the playable note set.
            if min(len(outline.notes) - len(skeleton.notes),
                   len(original.notes) - len(outline.notes)) <= len(original.notes) * .15:
                variants = (skeleton, original)
        notes = variants[-1].notes if variants else ()
        onsets = sorted({round(n.start, 6) for n in notes})
        trivial = (len(onsets) == len(notes)
                   and len(notes) <= max(1.0, exercise.phrase.end - exercise.phrase.start)
                   and all(b - a >= .5 - 1e-6 for a, b in zip(onsets, onsets[1:]))
                   and all(abs(n.start * 2 - round(n.start * 2)) < .05 for n in notes))
        return variants[-1:] if trivial else variants

    @classmethod
    def _stage_key(cls, exercise: Exercise, hand: str, variant: ExerciseVariant) -> str:
        phrase = variant.phrase
        events = [(n.start - phrase.start, n.end - phrase.start, n.pitch, n.track, n.channel, n.hand)
                  for n in phrase.notes]
        signature = hashlib.sha256(json.dumps((phrase.end - phrase.start, events),
                                             separators=(",", ":")).encode()).hexdigest()[:16]
        return f"course:{cls.route_version}:{exercise.key}:{hand}:{variant.level}:{signature}"

    @property
    def lesson_steps(self) -> tuple[LessonStep, ...]:
        """Build once; progress is across hands and levels, not MIDI measures."""
        if self._lesson_steps_cache is None:
            steps: list[LessonStep] = []
            for index, ex in enumerate(self.exercises):
                if ex.kind in ("learn", "warmup"):
                    available = {note.hand for note in ex.phrase.notes}
                    individual = tuple(hand for hand in ("right", "left") if hand in available)
                    hands = individual + (("both",) if len(individual) > 1 else ())
                else:
                    hands = ("both",)
                for hand in hands:
                    for variant in self._stage_variants(ex, hand):
                        steps.append(LessonStep(
                            index, hand, variant.level, self._stage_key(ex, hand, variant),
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
        return self._stage_key(self.exercise, self.hand, self.active_variant)

    def restore_location(self, *, kind: str, first_bar: int, last_bar: int,
                         hand: str, level: str) -> None:
        """Find saved source material in this course without reusing a stale index."""
        candidates = [(i, ex) for i, ex in enumerate(self.exercises)
                      if ex.phrase.first_bar <= first_bar and ex.phrase.last_bar >= last_bar]
        preferred = [(i, ex) for i, ex in candidates if ex.kind == kind]
        if not preferred:
            preferred = [(i, ex) for i, ex in candidates if ex.kind == "learn"]
        if preferred or candidates:
            self.select(min(preferred or candidates,
                            key=lambda pair: pair[1].phrase.last_bar - pair[1].phrase.first_bar)[0])
        if hand in self.hands:
            self.set_hand(hand)
        self.variant_index = next((i for i, variant in enumerate(self.variants) if variant.level == level), 0)

    def jump(self, amount: int) -> None:
        self.select(min(len(self.exercises) - 1, max(0, self.index + amount)))

    def select(self, index: int) -> None:
        if not 0 <= index < len(self.exercises):
            raise ValueError("Exercise index out of bounds")
        self.index = index
        self.hand_index = 0
        self.variant_index = 0
        self.bpm = self.start_bpm
        self.streak = 0
        self.failures = 0

    def set_hand(self, hand: str) -> None:
        if hand not in self.hands:
            raise ValueError(f"Hand {hand!r} unavailable")
        self.hand_index = self.hands.index(hand)
        self.variant_index = 0
        self.streak = self.failures = 0
        self.bpm = self.start_bpm

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

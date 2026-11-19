"""Owner practice flow course (docs/practice-flow.md): phrases, hands, links.

One piece is learned phrase by phrase. Every phrase and every link of two
neighbouring phrases is practised with the right hand, the left hand and both
hands together, always on the original notes. The piece ends with a final
whole-piece test. Simplified Coda/Fukuda exercises are not part of this
sequence; they are offered separately as an announced aid.
"""
from __future__ import annotations

from dataclasses import dataclass

from .adaptive_hybrid_curriculum import _SourceAttackIndex, _segments
from .exercise_generator import generate_variants
from .exercise_pipeline import ExerciseStage
from .lesson_settings import SETTINGS
from .lesson_source_planner import Exercise
from .music import Phrase, Piece
from .practice_windows import moving_windows, MAX_PRACTICE_BARS

MIN_PHRASE_BARS = 2
MAX_PHRASE_BARS = 4
# A cut after a rest of at least this many beats, or after a note held at
# least this long into the barline, is a natural phrase ending.
REST_CUT_BEATS = 0.5
HELD_CUT_BEATS = 1.0


def _natural_cut(piece: Piece, at: float) -> bool:
    """True when the music breathes at this barline: a rest, or a held note."""
    before = [n for n in piece.notes if n.start < at - 1e-7]
    if not before:
        return True
    if at - max(n.end for n in before) >= REST_CUT_BEATS - 1e-7:
        return True
    last_onset = max(n.start for n in before)
    return at - last_onset >= HELD_CUT_BEATS - 1e-7


def phrases(piece: Piece) -> tuple[Phrase, ...]:
    """Musical phrases of 2-4 bars built from safe 2-bar source units."""
    source = _SourceAttackIndex(piece)
    # Short source units (normally 2 bars; silent bars excluded). A unit is
    # extended when a note is held over its barline, so no phrase cuts a note.
    units = _segments(piece, source=source)
    grid = piece.bar_boundaries
    merged: list[tuple[int, int]] = []
    for unit in units:
        if merged:
            first, last = merged[-1]
            contiguous = last + 1 == unit.first_bar
            size = unit.last_bar - first + 1
            short = last - first + 1 < MIN_PHRASE_BARS
            if contiguous and size <= MAX_PHRASE_BARS and (
                    short or not _natural_cut(piece, grid[last])):
                merged[-1] = (first, unit.last_bar)
                continue
        merged.append((unit.first_bar, unit.last_bar))
    out = []
    for first, last in merged:
        start, end = grid[first - 1], grid[last]
        selected = source.notes_in(start - 1e-7, end - 1e-7)
        if not selected:
            continue
        out.append(Phrase(len(out) + 1, first, last, start,
                          max(end, max(n.end for n in selected)), selected))
    return tuple(out)


def _hands(notes) -> tuple[str, ...]:
    present = {n.hand for n in notes}
    hands = tuple(h for h in ("right", "left") if h in present)
    return hands + ("both",) if len(hands) == 2 else hands


def course_exercises(piece: Piece) -> tuple[Exercise, ...]:
    """Every bar alone, then 2/3/4-bar backwards-looking windows.

    Example: 1; 2, 1-2; 3, 2-3, 1-3; 4, 3-4, 2-4, 1-4;
    5, 4-5, 3-5, 2-5. The source retains its original timing and note
    IDs, including full holds beyond the final selected barline.
    """
    windows = moving_windows(piece, maximum_bars=MAX_PRACTICE_BARS)
    out: list[Exercise] = []
    for index, window in enumerate(windows, 1):
        phrase = window.phrase(index)
        out.append(Exercise("learn" if window.is_new_measure else "connect",
                            phrase, window.window_key,
                            hands=_hands(phrase.notes)))
    # Whole-piece verification is a separate final examination. It is
    # deliberately not a fifth-bar routine practice window.
    last = len(piece.bar_boundaries) - 1
    complete = Phrase(0, 1, last, piece.bar_boundaries[0],
                      max(piece.bar_boundaries[-1], max(n.end for n in piece.notes)),
                      piece.notes)
    out.append(Exercise("perform", complete, "flow:final", hands=("both",)))
    return tuple(out)


def original_stage(exercise: Exercise, hand: str) -> ExerciseStage:
    variants = generate_variants(exercise.phrase, hand,
                                 max_attacks=SETTINGS.focus_max_attacks)
    return ExerciseStage(variants[-1])


@dataclass(frozen=True)
class PracticeFlowLessonGenerator:
    """Real notes only, in the owner's phrase / hand / link order."""
    name: str = "practice-flow"
    # Tempo/timing rules of docs/practice-flow.md (teaching_decisions).
    flow_rules: bool = True

    def decide_teaching(self, event, state):
        from dataclasses import replace
        from .teaching_decisions import TeachingExposure, decide_standard_teaching
        decision = decide_standard_teaching(event, state, generator=self,
                                            allow_heuristic_remediation=False)
        course = state.course
        if event.kind == "guided_completed" and event.completed:
            # 2b -> 2c: every note found in order, Tempo starts by itself.
            exposure = TeachingExposure(
                course.key, course.hand, 0.0, None, decision.progress_after.bpm,
                "practice", False, True, False, "count_in")
            return replace(decision, next_exposure=exposure, continuation="continue")
        exposure = decision.next_exposure
        if exposure is not None and exposure.mode == "perform":
            # 4: the final test follows the same Tempo rules (50% -> target,
            # 2 clean), so it runs as timed practice, not as a review.
            exposure = replace(exposure, mode="practice")
            decision = replace(decision, next_exposure=exposure)
        from .application.practice_flow import Outcome
        if decision.flow_outcome is Outcome.BACK_TO_FREE and exposure is not None:
            # 2c: still failing at 50% -> play it without tempo again (2b).
            exposure = replace(exposure, from_beat=0.0, end_beat=None,
                               mode="learn", assisted=True, automatic=True,
                               require_full_verification=True,
                               preparation="count_in")
            return replace(decision, next_exposure=exposure, continuation="guided")
        if (exposure is not None and exposure.mode != "learn"
                and (exposure.stage_key, exposure.hand) != (course.key, course.hand)
                and ":flow:final:" not in exposure.stage_key):
            # A new hand, phrase or link starts at Listen -> Free, never
            # directly in tempo. The engine plays Listen before Free.
            exposure = replace(exposure, from_beat=0.0, end_beat=None,
                               mode="learn", assisted=True, automatic=True,
                               require_full_verification=True,
                               preparation="count_in")
            return replace(decision, next_exposure=exposure, continuation="guided")
        return decision

    def generate(self, piece: Piece):
        from .lesson_generators import LessonPlanDefinition
        exercises = course_exercises(piece)
        stages = {(ex.key, hand): (original_stage(ex, hand),)
                  for ex in exercises for hand in ex.hands}
        return LessonPlanDefinition(exercises, stages, self.name,
                                    requires_unique_source_ids=True)

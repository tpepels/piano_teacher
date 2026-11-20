"""Moving-window Practice Flow course on authentic authored MIDI notes.

Every new authored measure is introduced alone, then practised with up to
three preceding measures. Source IDs, long releases and their original
timing remain intact. Each window has its own hand sequence and mastery.
The whole-piece examination remains separate. Simplified Coda/Fukuda
material is an explicitly announced aid, never a hidden course stage.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .exercise_generator import generate_variants
from .exercise_pipeline import ExerciseStage
from .lesson_settings import SETTINGS
from .lesson_source_planner import Exercise
from .music import Phrase, Piece
from .practice_windows import moving_windows, MAX_PRACTICE_BARS

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


def _at_tempo(decision, bpm: int, *, reset: bool = False):
    """Commit one selected tempo to progress and its exact next exposure."""
    progress = decision.progress_after
    if reset or progress.bpm != bpm:
        progress = replace(progress,bpm=bpm,streak=0,failures=0)
    exposure = decision.next_exposure
    return replace(decision,progress_after=progress,
        next_exposure=replace(exposure,bpm=bpm) if exposure is not None else None)


def _entry_tempo(event, state, decision):
    exposure = decision.next_exposure
    if exposure is None:
        return decision
    if exposure.mode in ("listen","learn"):
        return _at_tempo(decision,int(decision.progress_after.target_bpm))
    exercise = decision.definition_after.exercises[decision.progress_after.cursor[0]]
    final_entry = (exercise.kind == "perform"
        and (exposure.stage_key != state.course.key
             or event.action in ("practice","perform","course_stage","open_at")))
    if (event.kind == "manual" and exposure.mode == "practice"
            and (state.route.mode in ("learn","listen") or final_entry)):
        from .application.practice_flow import floor_bpm
        return _at_tempo(decision,floor_bpm(int(decision.progress_after.target_bpm)),
                         reset=True)
    return decision


@dataclass(frozen=True)
class PracticeFlowLessonGenerator:
    """Real notes only, in the owner's phrase / hand / link order."""
    name: str = "practice-flow"
    # Tempo/timing rules of docs/practice-flow.md (teaching_decisions).
    flow_rules: bool = True

    def decide_teaching(self, event, state):
        from .teaching_decisions import TeachingExposure, decide_standard_teaching
        decision = decide_standard_teaching(event, state, generator=self,
                                            allow_heuristic_remediation=False)
        course = state.course
        if event.kind == "guided_completed" and event.completed:
            # 2b -> 2c: every note found in order, Tempo starts by itself.
            from .application.practice_flow import floor_bpm
            bpm = floor_bpm(int(decision.progress_after.target_bpm))
            exposure = TeachingExposure(
                course.key, course.hand, 0.0, None, bpm,
                "practice", False, True, False, "count_in")
            return _at_tempo(replace(decision,next_exposure=exposure,
                                     continuation="continue"),bpm,reset=True)
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
            return _entry_tempo(event,state,
                replace(decision,next_exposure=exposure,continuation="guided"))
        if (exposure is not None and exposure.mode != "learn"
                and (exposure.stage_key, exposure.hand) != (course.key, course.hand)
                and decision.definition_after.exercises[
                    decision.progress_after.cursor[0]].kind != "perform"):
            # A new hand or window starts at Listen -> Free, never
            # directly in tempo. The engine plays Listen before Free.
            exposure = replace(exposure, from_beat=0.0, end_beat=None,
                               mode="learn", assisted=True, automatic=True,
                               require_full_verification=True,
                               preparation="count_in")
            return _entry_tempo(event,state,
                replace(decision,next_exposure=exposure,continuation="guided"))
        return _entry_tempo(event,state,decision)

    def generate(self, piece: Piece):
        from .lesson_generators import LessonPlanDefinition
        exercises = course_exercises(piece)
        stages = {(ex.key, hand): (original_stage(ex, hand),)
                  for ex in exercises for hand in ex.hands}
        return LessonPlanDefinition(exercises, stages, self.name,
                                    requires_unique_source_ids=True)

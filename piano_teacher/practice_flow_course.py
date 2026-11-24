"""Practice Flow: the course structure and every "what happens next" rule.

Structure: every new authored measure is introduced alone, then practised
with up to three preceding measures; each window has its own hand sequence
and mastery, followed by a separate whole-piece final test. Source IDs,
long releases and original timing stay intact.

Decisions (docs/practice-flow.md) live in ``decide`` below: one function
from a teaching event (graded take, completed Free, learner command) to
the next exposure, tempo and progress. The tempo ladder itself is the pure
reducer in application/practice_flow.py. Simplified Coda/Fukuda material
is an explicitly announced aid on the second return to Free, never a
hidden course stage.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .exercise_generator import generate_variants
from .exercise_pipeline import ExerciseStage
from .lesson_settings import course_rules
from .lesson_contracts import Exercise, LessonPlanDefinition
from .music import Phrase, Piece
from .practice_windows import moving_windows, MAX_PRACTICE_BARS
from .lesson_generators import CodaAid, FukudaAid
from .teaching_decisions import (
    TeachingDecision, TeachingExposure, full_target_take,
)
from .teaching_course import at_position, next_unmastered
from .teaching_manual import choose_manual
from .application.assessment_verdict import AssessmentVerdict
from .application.practice_flow import (
    FlowState, Outcome, Step, floor_bpm, take_graded,
)

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
                      piece.bar_boundaries[-1],
                      piece.notes)
    out.append(Exercise("perform", complete, "flow:final", hands=("both",)))
    return tuple(out)


def original_stage(exercise: Exercise, hand: str) -> ExerciseStage:
    variants = generate_variants(exercise.phrase, hand,
                                 max_attacks=course_rules().focus_max_attacks)
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
    exercise = replace(state.course, progress=decision.progress_after).exercise
    final_entry = (exercise.kind == "perform"
        and (exposure.stage_key != state.course.key
             or event.action in ("practice","perform","course_stage","open_at")))
    if (event.kind == "manual" and exposure.mode == "practice"
            and (state.route.mode in ("learn","listen") or final_entry)):
        return _at_tempo(decision,floor_bpm(int(decision.progress_after.target_bpm)),
                         reset=True)
    return decision


# --- Decisions ---------------------------------------------------------


def graded_progress(course, *, accepted, secure=False):
    """One graded Tempo take, decided by the practice flow state machine
    (application/practice_py); this only maps it onto course progress."""
    p = course.progress
    state = FlowState(course.key, course.exercise.kind == "perform",
                           Step.TEMPO, int(p.bpm), int(p.target_bpm),
                           failures=p.failures, clean_at_target=p.streak,
                           free_returns=dict(p.free_returns).get(course.key,0))
    t = take_graded(state, passed=accepted, secure=secure)
    def selected(c, message):
        return c, message, t.outcome
    if t.outcome not in (Outcome.STAGE_DONE, Outcome.PIECE_DONE):
        bpm = p.bpm if t.outcome is Outcome.BACK_TO_FREE else t.state.bpm
        returns = dict(p.free_returns)
        if t.outcome is Outcome.BACK_TO_FREE:
            returns[course.key] = t.state.free_returns
        return selected(course.with_progress(bpm=bpm, failures=t.state.failures,
                                    streak=t.state.clean_at_target,
                                    free_returns=tuple(sorted(returns.items()))), t.message)
    mastered = dict(p.mastered)
    mastered[course.key] = p.target_bpm
    course = course.with_progress(streak=0, failures=0,
                                  mastered=tuple(sorted(mastered.items())))
    if t.outcome is Outcome.PIECE_DONE:
        return selected(course, t.message)
    # The next step not yet mastered (after a jump back, mastered windows
    # are skipped).
    following = next_unmastered(course)
    if following is None:
        return selected(course, "Piece mastered")
    course = at_position(course, following)
    return selected(course.with_progress(bpm=floor_bpm(int(p.target_bpm))), t.message)


def _base_decision(event, state):
    """The take/command outcome before Practice Flow's step rules apply."""
    c, route, result = state.course, state.route, event.assessment
    chosen, message = c, ""
    continuation = "continue"
    eligible = full_target_take(event, state)
    verdict = (AssessmentVerdict.decide(result, policy="practice-flow", eligible=eligible)
               if result is not None else None)
    passed = verdict.accepted if verdict is not None else False
    flow_outcome = None
    manual_exposure = None
    if event.kind == "manual":
        chosen,start,end,mode,continuation = choose_manual(event,state)
        manual_exposure = start,end,mode
    elif event.kind == "interrupted":
        continuation = "stop"
    elif event.kind in ("full_result", "focused_result"):
        if eligible:
            chosen, message, flow_outcome = graded_progress(
                c, accepted=passed, secure=passed and result.secure)
        if (not route.automatic or flow_outcome is Outcome.PIECE_DONE
                or route.scope in ("perform", "section_review")):
            continuation = "stop"
        elif chosen.key != c.key:
            continuation = "advance"
        elif event.kind == "focused_result":
            continuation = "reintegrate"
        else:
            continuation = "repeat"
    elif event.kind == "guided_completed":
        continuation = "stop" if event.completed else "guided"
    else:
        raise ValueError("Unsupported teaching event")
    exposure = None
    if continuation not in ("stop", "pause"):
        start = event.from_beat if event.from_beat is not None else 0.
        end = event.end_beat
        mode = "learn" if continuation == "guided" else route.mode
        if manual_exposure is not None:
            start,end,mode = manual_exposure
        elif event.kind == "guided_completed":
            mode = "practice"
            if route.guided_return is not None:
                start, end = route.guided_return[1], None
        automatic = mode == "practice" if event.kind == "manual" and event.action in ("start","restart","practice","course_stage","open_at") else route.automatic
        restart = (event.kind == "manual" and event.action == "restart"
                   and route.mode == "practice" and c.exercise.kind != "perform")
        exposure = TeachingExposure(chosen.key, chosen.hand, start, end, chosen.progress.bpm, mode,
            mode == "learn", automatic, bool(start or end is not None or mode == "learn"),
            "handoff" if chosen.key != c.key else "rewind" if restart else "count_in")
    return TeachingDecision(1, event.event_id+":teaching", event.event_id, state.binding,
        c.progress, chosen.definition, chosen.progress, None, exposure, continuation,
        eligible and not passed, eligible and route.performed_bpm >= c.progress.target_bpm,
        "course_progression", message, flow_outcome, verdict)


def decide(event, state, *, aid) -> TeachingDecision:
    """The one Practice Flow decision for a teaching event."""
    decision = _base_decision(event, state)
    course = state.course
    if (event.kind == "manual" and decision.next_exposure is not None
            and decision.next_exposure.mode == "learn"
            and decision.continuation == "guided"):
        # Free is the complete selected window, including resumed final
        # examinations.
        exposure = replace(decision.next_exposure,from_beat=0.0,
            end_beat=None,assisted=True)
        decision = replace(decision,next_exposure=exposure)
    if event.kind == "guided_completed" and event.completed:
        if state.route.guided_range != (0.0,course.stage.variant.phrase.end-course.stage.variant.phrase.start):
            raise ValueError("Free must find every attack in the selected window")
        if state.route.remediation_active:
            # The aid earns no source credit. Find every real note again
            # before returning to the source's Tempo ladder.
            exposure = TeachingExposure(course.key,course.hand,0.0,None,
                int(course.progress.target_bpm),"learn",True,True,True,"count_in")
            return _at_tempo(replace(decision,next_exposure=exposure,
                continuation="guided",message="Now the original notes · without tempo"),
                int(course.progress.target_bpm),reset=True)
        # 2b -> 2c: every note found in order, Tempo starts by itself.
        bpm = floor_bpm(int(decision.progress_after.target_bpm))
        exposure = TeachingExposure(
            course.key, course.hand, course.stage.variant.phrase.first_attack_beat, None, bpm,
            "practice", False, True, False, "count_in")
        return _at_tempo(replace(decision,next_exposure=exposure,
                                 continuation="continue"),bpm,reset=True)
    exposure = decision.next_exposure
    if exposure is not None and exposure.mode == "perform":
        # 4: the final test follows the same Tempo rules (50% -> target,
        # 2 clean), so it runs as timed practice, not as a review.
        exposure = replace(exposure, mode="practice")
        decision = replace(decision, next_exposure=exposure)
    if decision.flow_outcome is Outcome.BACK_TO_FREE and exposure is not None:
        # 2c: still failing at 50% -> play it without tempo again (2b).
        exposure = replace(exposure, from_beat=0.0, end_beat=None,
                           mode="learn", assisted=True, automatic=True,
                           require_full_verification=True,
                           preparation="count_in")
        simplified = (aid(course,event.assessment)
               if dict(decision.progress_after.free_returns).get(course.key,0) == 2 else None)
        return _entry_tempo(event,state,
            replace(decision,next_exposure=exposure,continuation="guided",
                remediation=simplified,
                message=simplified.focus if simplified is not None else decision.message))
    after = replace(course, progress=decision.progress_after)
    if (exposure is not None and exposure.mode != "learn"
            and (exposure.stage_key, exposure.hand) != (course.key, course.hand)
            and after.step.kind != "perform"):
        # A new hand or window starts at Listen -> Free, never
        # directly in tempo. The engine plays Listen before Free.
        exposure = replace(exposure, from_beat=0.0, end_beat=None,
                           mode="learn", assisted=True, automatic=True,
                           require_full_verification=True,
                           preparation="count_in")
        return _entry_tempo(event,state,
            replace(decision,next_exposure=exposure,continuation="guided"))
    decision = _entry_tempo(event,state,decision)
    exposure = decision.next_exposure
    if (exposure is not None and exposure.mode == "practice"
            and exposure.from_beat == 0 and exposure.end_beat is None):
        source = after.stage.variant.phrase
        decision = replace(decision,next_exposure=replace(exposure,
            from_beat=source.first_attack_beat))
    return decision


# Part of every saved stage key ("course:2:practice-flow:..."): changing it
# would orphan saved progress.
COURSE_VERSION = 2


@dataclass(frozen=True)
class PracticeFlowLessonGenerator:
    """Real notes only, in the owner's phrase / hand / link order."""
    components: tuple = (FukudaAid(), CodaAid())
    name: str = "practice-flow"

    def _simplified_aid(self, course, result):
        """Ask existing MIDI contributors for this exact source window/hand."""
        from .lesson_stage_semantics import teaching_sequence
        from .remediation import RemedialAssignment
        original = course.stage.variant
        evidence = {entry.note.source_id:entry.status for entry in result.notes
                    if entry.status != "correct"}
        candidates = []
        for contributor in self.components:
            feedback = getattr(contributor,"with_feedback",None)
            if callable(feedback):
                contributor = feedback(evidence,course.definition)
            candidates.extend(contributor.passage_stages(
                course.piece,original,kind="learn")[:-1])
        chosen = teaching_sequence((*candidates,course.stage),evidence=evidence)
        # Free can teach reduced attacks and chord groupings. A tempo-only
        # variant would be inaudibly identical in an untimed exercise.
        aid = next((stage for stage in chosen
            if stage.variant.notes != original.notes),None)
        if aid is None:
            return None
        return RemedialAssignment("note-isolation",
            f"Simplified: {aid.display_name}",0.0,
            original.phrase.end-original.phrase.start,aid.variant,course.key,
            "second_return_to_free",aid.transformed_rhythm)

    def decide_teaching(self, event, state):
        return decide(event, state, aid=self._simplified_aid)

    def generate(self, piece: Piece):
        exercises = course_exercises(piece)
        stages = {(ex.key, hand): (original_stage(ex, hand),)
                  for ex in exercises for hand in ex.hands}
        return LessonPlanDefinition(exercises, stages, self.name,
                                    requires_unique_source_ids=True)


# --- Checkpoints ---------------------------------------------------------

CHECKPOINT_BARS = 4
_checkpoint_keys: dict[int, tuple] = {}


def _keys_by_checkpoint(course):
    """Step keys grouped by the checkpoint their window's last bar falls in,
    and one measure preview per checkpoint (cached per definition)."""
    definition = course.definition
    cached = _checkpoint_keys.get(id(definition))
    if cached is not None and cached[0] is definition:
        return cached[1]
    groups: dict[int, set[str]] = {}
    for step in course.steps:
        if step.kind == "learn":
            first = 1 + (step.last_bar-1)//CHECKPOINT_BARS*CHECKPOINT_BARS
            groups.setdefault(first, set()).add(step.key)
    keys = {bar: frozenset(group) for bar, group in groups.items()}
    previews = {bar: _measure_preview(course.piece, bar)
                for bar in range(1, len(course.piece.bar_boundaries), CHECKPOINT_BARS)}
    if len(_checkpoint_keys) > 4:
        _checkpoint_keys.clear()
    _checkpoint_keys[id(definition)] = (definition, (keys, previews))
    return keys, previews


_NATURAL_STEP = (0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6)  # pitch class -> letter


def _measure_preview(piece, bar: int) -> dict:
    """A thumbnail of one measure: its right-hand notes on a treble staff
    (left hand on bass if the right is silent) as (x 0..1, staff step),
    step 0 = bottom line, 8 = top line. Accidentals are not drawn."""
    start, end = piece.bar_boundaries[bar-1], piece.bar_boundaries[bar]
    notes = [n for n in piece.notes if start-1e-7 <= n.start < end-1e-7]
    hand = "right" if any(n.hand == "right" for n in notes) else "left"
    bottom = 30 if hand == "right" else 18  # E4 / G2 as diatonic indices
    heads = []
    for n in notes:
        if n.hand != hand:
            continue
        step = (n.pitch//12)*7 + _NATURAL_STEP[n.pitch % 12] - bottom
        heads.append([round((n.start-start)/max(1e-6, end-start), 3),
                      max(-6, min(14, step))])
    return {"clef": "treble" if hand == "right" else "bass", "notes": heads[:24]}


def checkpoints(course) -> list[dict]:
    """Every fourth measure (1, 5, 9, ...) is a place to jump to in the
    piece. A checkpoint is complete when every window that ends in its
    measures is mastered for every hand; ``current`` holds the window being
    practised. Jumping uses open_at (that measure's window, from Listen)."""
    last_bar = len(course.piece.bar_boundaries)-1
    mastered = dict(course.progress.mastered)
    keys, previews = _keys_by_checkpoint(course)
    exercise = course.exercise
    here = exercise.phrase.last_bar if exercise.kind == "learn" else None
    rows = []
    for first in range(1, last_bar+1, CHECKPOINT_BARS):
        last = min(last_bar, first+CHECKPOINT_BARS-1)
        group = keys.get(first, frozenset())
        rows.append({"bar": first, "last_bar": last,
                     "complete": bool(group) and group <= mastered.keys(),
                     "current": here is not None and first <= here <= last,
                     "preview": previews.get(first, {"clef": "treble", "notes": []})})
    return rows

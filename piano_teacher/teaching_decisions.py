"""One immutable pedagogical choice from the selected lesson generator.

The application captures facts and installs effects. Retry/source/tempo and
mastery choices live here, before any announcement or durable mutation.
"""
from __future__ import annotations
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from math import isfinite
from .teaching_course import (PlanProgress, CourseState, assessed_progress, manual_progress,
    refresh_course, revisit_course, minimum_bpm, steps, preserve_mastered)
from .lesson_generators import LessonPlanDefinition
from .practice import Assessment
from .music import Piece
from .diagnosis_policies import (LearnerSnapshot, AssessmentEvidence,
    ErrorFamilyDiagnosis, RepeatedErrorPolicy)
from .remediation import RemedialAssignment, RemediationPlanner
from .measure_grid import phrase_grid
from .application.mistake_responses import (MistakePolicy, AdaptiveContext, WholeResponse,
    RollingResponse, whole_response, rolling_response)
from .application.stage_change import StageChange
from .recovery import RecoveryDecision
from .lesson_settings import SETTINGS
from .teaching_manual import ManualFacts, choose_manual, next_guided_range


@dataclass(frozen=True, slots=True)
class TeachingBinding:
    run_id: str
    session_id: str
    fingerprint: str
    stage_key: str
    course_revision: int
    authority_revision: int
    transport_id: int
    cancellation_generation: int


@dataclass(frozen=True, slots=True)
class TeachingEvent:
    version: int
    event_id: str
    kind: str
    attempt_id: str | None = None
    assessment: Assessment | None = None
    rolling: RecoveryDecision | None = None
    manual: StageChange | None = None
    action: str | None = None
    from_beat: float | None = None
    end_beat: float | None = None
    assisted_count: int = 0
    completed: bool = False
    reason: str | None = None
    bar: int | None = None
    first_bar: int | None = None
    last_bar: int | None = None
    scope: str | None = None
    requested_stage: str | None = None
    requested_mode: str | None = None


@dataclass(frozen=True, slots=True)
class TeachingRouteFacts:
    mode: str = "practice"
    automatic: bool = False
    warmup: bool = False
    preview_only: bool = False
    assistance_used: bool = False
    scope: str = "full_passage"
    performed_bpm: int = 120
    from_beat: float = 0.
    end_beat: float = 0.
    course_guided: bool = False
    guided_return: tuple[str, float] | None = None
    guided_range: tuple[float, float] | None = None
    review_end_beat: float | None = None
    remediation_active: bool = False
    trouble_key: tuple | None = None
    trouble_count: int = 0
    parent_decision_id: str | None = None
    episode_action_count: int = 0


@dataclass(frozen=True, slots=True)
class TeachingState:
    version: int
    binding: TeachingBinding
    course: CourseState
    policy: MistakePolicy
    source_feedback: tuple[tuple[str, str], ...]
    diagnosis: LearnerSnapshot
    retry_context: AdaptiveContext | None
    route: TeachingRouteFacts
    diagnosis_strategy: object = ErrorFamilyDiagnosis()
    learner_strategy: object = RepeatedErrorPolicy()
    catalog: LessonPlanDefinition | None = None
    manual_facts: ManualFacts = ManualFacts()

    @property
    def progress(self):
        return self.course.progress

    @property
    def piece(self):
        return self.course.piece

    @property
    def definition(self):
        return self.course.definition


@dataclass(frozen=True, slots=True)
class TeachingExposure:
    stage_key: str
    hand: str
    from_beat: float
    end_beat: float | None
    bpm: int
    mode: str
    assisted: bool
    automatic: bool
    require_full_verification: bool
    preparation: str


@dataclass(frozen=True, slots=True)
class TeachingDecision:
    version: int
    decision_id: str
    event_id: str
    expected: TeachingBinding
    before_progress: PlanProgress
    definition_after: LessonPlanDefinition
    progress_after: PlanProgress
    feedback_after: tuple[tuple[str, str], ...]
    response: WholeResponse | RollingResponse | None
    remediation: RemedialAssignment | None
    next_exposure: TeachingExposure | None
    continuation: str
    invalidate_failed_streak: bool
    mastery_eligible: bool
    reason: str
    message: str


def source_safe_response(response, *, phrase, hand, grid):
    """Expand bounded source measures so no authored hold is cut."""
    if response.end_beat is None or response.action in ("continue", "pause"):
        return response
    start, end = response.restart_beat, response.end_beat
    notes = tuple(n for n in phrase.notes if hand == "both" or n.hand == hand)
    while start > grid[0] and any(n.start < phrase.start+start-1e-7 < n.end-1e-7 for n in notes):
        # Whole-take policy permits restarting at the current playback beat,
        # which need not coincide with an authored measure boundary. The old
        # grid.index(start) raised ValueError if a held note crossed that beat.
        previous = bisect_left(grid, start-1e-7) - 1
        if previous < 0:
            break
        start = grid[previous]
    while end < grid[-1] and any(phrase.start+start-1e-7 <= n.start < phrase.start+end-1e-7
            and n.end > phrase.start+end+1e-7 for n in notes):
        following = bisect_right(grid, end+1e-7)
        if following >= len(grid):
            break
        end = grid[following]
    return replace(response, restart_beat=start, end_beat=end)


def decide_standard_teaching(event, state, *, generator=None):
    c, route, result = state.course, state.route, event.assessment
    chosen, message = c, ""
    response = remediation = None
    feedback = dict(state.source_feedback)
    continuation = "continue"
    eligible = (event.kind == "full_result" and route.mode == "practice"
        and not route.preview_only and not route.assistance_used and route.from_beat == 0
        and route.review_end_beat is None and bool(result and result.notes))
    invalidate = eligible and not result.passed
    phrase = c.stage.variant.phrase
    grid = tuple(phrase_grid(phrase, c.piece.bar_boundaries))
    manual_exposure = None
    if event.kind == "manual":
        chosen,start,end,mode,continuation = choose_manual(event,state)
        manual_exposure = start,end,mode
    elif event.kind == "interrupted":
        continuation = "stop"
    elif event.kind == "rolling_result":
        response = rolling_response(state.policy, event.rolling, identity=c.key,
            bpm=c.progress.bpm, minimum_bpm=min(c.progress.bpm, minimum_bpm(c)),
            previous_key=route.trouble_key, previous_count=route.trouble_count,
            grid=grid, allow_guided=not route.automatic, context=state.retry_context)
        safe = source_safe_response(response, phrase=phrase, hand=c.hand, grid=grid)
        if response.action == "isolate" and safe != response:
            response = replace(response, action="continue", reason="source_hold_requires_full_target")
        if response.action != "continue":
            chosen = c.with_progress(bpm=response.bpm, streak=0, failures=c.progress.failures+1)
            continuation = "guided" if response.guided else "pause" if response.action == "pause" else "repair"
    elif event.kind in ("full_result", "focused_result"):
        full_retry = (event.kind == "full_result" and route.automatic and not result.passed
                      and not route.warmup)
        focused_retry = (event.kind == "focused_result" and route.automatic
            and route.scope in ("section_review", "partial_recovery")
            and state.policy.whole_handler is not None and route.parent_decision_id is not None)
        if full_retry or focused_retry:
            response = whole_response(state.policy, result, phrase=phrase, grid=grid,
                bpm=c.progress.bpm, minimum_bpm=min(c.progress.bpm, minimum_bpm(c)),
                play_from_beat=route.from_beat, context=state.retry_context)
            if state.policy.whole_handler is not None:
                response = source_safe_response(response, phrase=phrase, hand=c.hand, grid=grid)
        if eligible:
            chosen, message = assessed_progress(c, correct=result.correct, total=len(result.notes),
                                                extras=result.extra_notes, accepted=result.passed)
        if response is not None:
            chosen = chosen.with_progress(bpm=response.bpm)
        if (eligible and not result.passed and route.automatic and not route.warmup
                and c.exercise.kind == "learn" and state.policy.whole_handler is None):
            evidence = AssessmentEvidence.from_result(c.key, result, route.performed_bpm)
            history = LearnerSnapshot(c.key, (state.diagnosis.recent + (evidence,))[-8:])
            recommendation = state.learner_strategy.recommend(history, state.diagnosis_strategy)
            remediation = RemediationPlanner().plan(recommendation, result, c.stage.variant,
                stage_key=c.key, boundaries=c.piece.bar_boundaries) if recommendation else None
        hook = getattr(generator, "with_feedback", None)
        if (eligible and callable(hook) and c.stage.variant.level == "original" and not route.warmup):
            for entry in result.notes:
                if entry.status == "correct":
                    feedback.pop(entry.note.source_id, None)
                else:
                    feedback[entry.note.source_id] = entry.status
            failed_ids = frozenset(n.note.source_id for n in result.notes if n.status != "correct")
            updated = hook(feedback, c.definition)
            before_source = chosen.key
            if updated is not generator:
                chosen = refresh_course(chosen, updated.generate(c.piece),
                    focus_ids=failed_ids if not result.passed else frozenset())
            elif not result.passed:
                chosen = revisit_course(chosen, failed_ids)
            if chosen.key != before_source:
                remediation = response = None
        if not route.automatic or message == "Piece mastered" or (route.warmup and not result.passed) or route.scope in ("perform", "section_review") and response is None:
            continuation = "stop"
        elif response is not None:
            continuation = "guided" if response.guided else "pause" if response.action == "pause" else "repair"
        elif remediation is not None:
            continuation = "guided" if remediation.guided and not route.automatic else "repair"
        elif chosen.key != c.key:
            continuation = "advance"
        elif event.kind == "focused_result":
            continuation = "reintegrate"
        else:
            continuation = "repeat"
    elif event.kind == "guided_completed":
        continuation = "stop" if event.completed else "guided"
    elif event.kind != "source_feedback_changed":
        raise ValueError("Unsupported teaching event")
    exposure = None
    if continuation not in ("stop", "pause"):
        start = response.restart_beat if response else remediation.start_beat if remediation else (
            event.from_beat if event.from_beat is not None else 0.)
        end = response.end_beat if response else remediation.end_beat if remediation else event.end_beat
        mode = "learn" if continuation == "guided" else route.mode
        if manual_exposure is not None:
            start,end,mode = manual_exposure
        elif event.kind == "guided_completed":
            mode = "practice"
            if route.guided_return is not None:
                start = route.guided_return[1]
                end = route.guided_range[1] if state.policy.whole_handler is not None and route.guided_range else None
        elif chosen.key != c.key and route.course_guided and route.mode == "learn":
            selected = next_guided_range(chosen,state.manual_facts.credits)
            if chosen.exercise.kind == "perform":
                mode = "perform"
            elif selected is not None:
                start,end = selected
                mode = "learn"
        automatic = mode == "practice" if event.kind == "manual" and event.action in ("start","restart","practice","learn_next","course_stage","open_at") else route.automatic
        exposure = TeachingExposure(chosen.key, chosen.hand, start, end, chosen.progress.bpm, mode,
            mode == "learn", automatic, bool(start or end is not None or mode == "learn"),
            "handoff" if chosen.key != c.key else "rewind" if response or (event.kind == "manual" and event.action == "restart" and route.mode == "practice" and c.exercise.kind != "perform") else "count_in")
    return TeachingDecision(1, event.event_id+":teaching", event.event_id, state.binding,
        c.progress, chosen.definition, chosen.progress, tuple(sorted(feedback.items())), response,
        remediation, exposure, continuation, invalidate, eligible and route.performed_bpm >= c.progress.target_bpm,
        response.reason if response else "course_progression", message)


def decide_coda_fukuda_teaching(event, state, *, generator):
    return decide_standard_teaching(event, state, generator=generator)


def validate_teaching_decision(decision, *, event, state):
    """Reject unsafe/stale/unearned effects, without selecting another policy."""
    if not isinstance(decision, TeachingDecision) or decision.version != 1 or event.version != 1 or state.version != 1:
        raise ValueError("Unsupported teaching decision version")
    if (decision.expected != state.binding or decision.before_progress != state.progress
            or decision.event_id != event.event_id or not decision.decision_id):
        raise ValueError("Stale teaching decision binding/progress")
    if event.kind not in {"full_result", "focused_result", "rolling_result", "guided_completed", "manual", "source_feedback_changed", "interrupted"}:
        raise ValueError("Unsupported teaching event kind")
    if (event.kind in {"full_result", "focused_result", "rolling_result"}) != (event.assessment is not None):
        raise ValueError("Teaching assessment payload mismatch")
    if (event.kind == "rolling_result") != (event.rolling is not None):
        raise ValueError("Teaching rolling payload mismatch")
    if event.manual is not None and event.kind != "manual":
        raise ValueError("Teaching manual payload mismatch")
    if decision.definition_after.generator_name != state.definition.generator_name or decision.definition_after.exercises != state.definition.exercises:
        raise ValueError("Unknown teaching source/course")
    catalog = state.catalog
    if catalog is not None:
        for stage_key, sequence in decision.definition_after.stage_sequences.items():
            allowed = catalog.stage_sequences.get(stage_key, ()) + state.definition.stage_sequences.get(stage_key, ())
            if any(stage not in allowed for stage in sequence):
                raise ValueError("Unknown teaching catalog candidate")
    p = decision.progress_after
    if (type(p.cursor) is not tuple or len(p.cursor) != 3
            or any(type(value) is not tuple for value in (p.mastered,p.stage_tempos,p.transferable_tempos))
            or type(decision.feedback_after) is not tuple):
        raise ValueError("Mutable teaching progress")
    for value in (p.bpm, p.target_bpm):
        if type(value) not in (int, float) or not isfinite(value) or not SETTINGS.minimum_bpm <= value <= SETTINGS.maximum_bpm:
            raise ValueError("Invalid teaching BPM")
    if any(type(value) is not int or value < 0 for value in (*p.cursor, p.streak, p.failures)):
        raise ValueError("Invalid teaching progress")
    chosen = replace(state.course, definition=decision.definition_after, progress=p)
    try:
        key, hand, phrase = chosen.key, chosen.hand, chosen.stage.variant.phrase
    except (IndexError, KeyError):
        raise ValueError("Unavailable teaching stage/hand") from None
    available = {s[3] for s in steps(chosen)}
    if not set(dict(p.mastered)) <= available:
        raise ValueError("Unknown mastered teaching stage")
    if preserve_mastered(state.course, decision.definition_after) != decision.definition_after:
        raise ValueError("Teaching decision changed a mastered definition")
    earned = set(dict(p.mastered)) - set(dict(state.progress.mastered))
    eligible = (event.kind == "full_result" and state.route.mode == "practice"
        and not state.route.preview_only and not state.route.assistance_used
        and state.route.from_beat == 0 and state.route.review_end_beat is None
        and event.assessment is not None and bool(event.assessment.notes) and event.assessment.passed
        and state.route.performed_bpm >= state.progress.target_bpm
        and state.progress.streak+1 >= SETTINGS.clean_runs_to_master)
    if earned and (not eligible or earned != {state.course.key}):
        raise ValueError("Unearned teaching mastery")
    full_target = (event.kind == "full_result" and state.route.mode == "practice"
        and not state.route.preview_only and not state.route.assistance_used
        and state.route.from_beat == 0 and state.route.review_end_beat is None
        and event.assessment is not None and bool(event.assessment.notes))
    if decision.invalidate_failed_streak != bool(full_target and not event.assessment.passed):
        raise ValueError("Invalid failed-streak checkpoint")
    if not full_target and (p.streak > state.progress.streak or earned or decision.invalidate_failed_streak):
        raise ValueError("Partial teaching event cannot earn full-target credit")
    if decision.continuation not in {"continue", "repeat", "repair", "reintegrate", "advance", "guided", "stop", "pause"}:
        raise ValueError("Invalid teaching continuation")
    if event.kind == "manual" and event.action in ("pause", "stop") and decision.continuation != event.action:
        raise ValueError("Teaching decision violates explicit stop/pause")
    for entries in (p.mastered,p.stage_tempos):
        if any(type(entry) is not tuple or len(entry) != 2 or type(entry[0]) is not str
                or type(entry[1]) not in (int,float) or not isfinite(entry[1])
                or not SETTINGS.minimum_bpm <= entry[1] <= SETTINGS.maximum_bpm for entry in entries):
            raise ValueError("Invalid recorded teaching tempo")
    exposure = decision.next_exposure
    if (decision.continuation in ("stop","pause")) != (exposure is None):
        raise ValueError("Teaching continuation/exposure mismatch")
    if event.kind == "manual" and event.manual is not None:
        manual = event.manual
        if manual.action == "select_step" and p.cursor != steps(state.course)[manual.number-1][:3]:
            raise ValueError("Teaching decision violates selected stage")
        if manual.action == "hand" and hand != manual.hand:
            raise ValueError("Teaching decision violates selected hand")
    if exposure is not None:
        if exposure.mode not in ("practice","learn","listen","perform") or exposure.preparation not in ("none","count_in","rewind","handoff"):
            raise ValueError("Invalid teaching exposure mode/preparation")
        if exposure.mode == "listen" and (exposure.from_beat != 0 or exposure.end_beat is not None):
            raise ValueError("Listen requires the complete selected source")
        if exposure.stage_key != key or exposure.hand != hand or exposure.bpm != p.bpm:
            raise ValueError("Teaching exposure destination mismatch")
        end = phrase.end-phrase.start if exposure.end_beat is None else exposure.end_beat
        if any(type(v) not in (int, float) or not isfinite(v) for v in (exposure.from_beat, end)) or not 0 <= exposure.from_beat < end <= phrase.end-phrase.start:
            raise ValueError("Invalid teaching source range")
        if exposure.end_beat is not None and exposure.mode != "learn":
            notes = tuple(n for n in phrase.notes if hand == "both" or n.hand == hand)
            start = exposure.from_beat
            if any(n.start < phrase.start+start-1e-7 < n.end-1e-7 or
                   phrase.start+start-1e-7 <= n.start < phrase.start+end-1e-7 and n.end > phrase.start+end+1e-7 for n in notes):
                raise ValueError("Teaching source range cuts a held note")

"""One immutable Practice Flow decision about what happens next.

The application captures facts and installs effects. Tempo, stage and
mastery choices live here, before any announcement or durable mutation.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from math import isfinite
from .teaching_course import PlanProgress, CourseState
from .lesson_contracts import LessonPlanDefinition
from .practice import Assessment
from .remediation import RemedialAssignment
from .application.stage_change import StageChange
from .lesson_settings import SETTINGS
from .teaching_manual import ManualFacts
from .application.assessment_verdict import AssessmentVerdict
from .application.practice_flow import Outcome


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
    assistance_used: bool = False
    scope: str = "full_passage"
    performed_bpm: int = 120
    from_beat: float = 0.
    end_beat: float = 0.
    course_guided: bool = False
    guided_return: tuple[str, float] | None = None
    guided_range: tuple[float, float] | None = None
    remediation_active: bool = False
    parent_decision_id: str | None = None
    episode_action_count: int = 0


@dataclass(frozen=True, slots=True)
class TeachingState:
    version: int
    binding: TeachingBinding
    course: CourseState
    route: TeachingRouteFacts
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
    remediation: RemedialAssignment | None
    next_exposure: TeachingExposure | None
    continuation: str
    invalidate_failed_streak: bool
    mastery_eligible: bool
    reason: str
    message: str
    flow_outcome: Outcome | None = None
    verdict: AssessmentVerdict | None = None


def full_source_opening(state) -> bool:
    """Skipping source silence cannot turn a complete take into a partial one."""
    return (abs(state.route.from_beat) <= 1e-7 or
        abs(state.route.from_beat-state.course.stage.variant.phrase.first_attack_beat) <= 1e-7)


def full_target_take(event, state) -> bool:
    """A complete graded Tempo take of the selected window (mastery-eligible)."""
    route, result = state.route, event.assessment
    return (event.kind == "full_result" and route.mode == "practice"
        and not route.assistance_used
        and full_source_opening(state)
        and bool(result and result.notes))


def validate_teaching_decision(decision, *, event, state):
    """Reject unsafe/stale/unearned effects, without selecting another policy."""
    if not isinstance(decision, TeachingDecision) or decision.version != 1 or event.version != 1 or state.version != 1:
        raise ValueError("Unsupported teaching decision version")
    if (decision.expected != state.binding or decision.before_progress != state.progress
            or decision.event_id != event.event_id or not decision.decision_id):
        raise ValueError("Stale teaching decision binding/progress")
    if event.kind not in {"full_result", "focused_result", "guided_completed", "manual", "interrupted"}:
        raise ValueError("Unsupported teaching event kind")
    if (event.kind in {"full_result", "focused_result"}) != (event.assessment is not None):
        raise ValueError("Teaching assessment payload mismatch")
    if event.manual is not None and event.kind != "manual":
        raise ValueError("Teaching manual payload mismatch")
    if decision.definition_after.generator_name != state.definition.generator_name or decision.definition_after.exercises != state.definition.exercises:
        raise ValueError("Unknown teaching source/course")
    p = decision.progress_after
    lower_bpm = 1
    if any(type(value) is not tuple for value in (p.mastered, p.free_returns)):
        raise ValueError("Mutable teaching progress")
    for value in (p.bpm, p.target_bpm):
        if type(value) not in (int, float) or not isfinite(value) or not lower_bpm <= value <= SETTINGS.maximum_bpm:
            raise ValueError("Invalid teaching BPM")
    if any(type(value) is not int or value < 0 for value in (p.position, p.streak, p.failures)):
        raise ValueError("Invalid teaching progress")
    if any(type(key) is not str or type(count) is not int or count < 0
           for key,count in p.free_returns):
        raise ValueError("Invalid Free return history")
    chosen = replace(state.course, definition=decision.definition_after, progress=p)
    try:
        key, hand, phrase = chosen.key, chosen.hand, chosen.stage.variant.phrase
    except (IndexError, KeyError):
        raise ValueError("Unavailable teaching stage/hand") from None
    if decision.definition_after is not state.definition:
        raise ValueError("A teaching decision cannot replace the course")
    available = {step.key for step in chosen.steps}
    if not set(dict(p.mastered)) <= available:
        raise ValueError("Unknown mastered teaching stage")
    earned = set(dict(p.mastered)) - set(dict(state.progress.mastered))
    # Practice flow (docs/practice-flow.md): timing fails only when clearly
    # off, and two clean takes in a row at the target tempo finish a step.
    passed = bool(decision.verdict and decision.verdict.accepted)
    full_target = full_target_take(event, state)
    if event.assessment is not None:
        expected_verdict = AssessmentVerdict.decide(
            event.assessment, policy="practice-flow", eligible=full_target)
        if decision.verdict != expected_verdict:
            raise ValueError("Teaching and settlement disagree on assessment policy")
    eligible = (full_target and passed
        and state.route.performed_bpm >= state.progress.target_bpm
        and state.progress.streak+1 >= state.course.clean_runs_required)
    if earned and (not eligible or earned != {state.course.key}):
        raise ValueError("Unearned teaching mastery")
    ignored = bool(decision.verdict and decision.verdict.ignored)
    if ignored and (p != state.progress or decision.mastery_eligible or decision.remediation is not None):
        raise ValueError("Ignored take cannot alter learning progress")
    if decision.invalidate_failed_streak != bool(full_target and not passed and not ignored):
        raise ValueError("Invalid failed-streak checkpoint")
    if not full_target and (p.streak > state.progress.streak or earned or decision.invalidate_failed_streak):
        raise ValueError("Partial teaching event cannot earn full-target credit")
    if decision.continuation not in {"continue", "repeat", "reintegrate", "advance", "guided", "stop", "pause"}:
        raise ValueError("Invalid teaching continuation")
    if event.kind == "manual" and event.action in ("pause", "stop") and decision.continuation != event.action:
        raise ValueError("Teaching decision violates explicit stop/pause")
    if any(type(entry) is not tuple or len(entry) != 2 or type(entry[0]) is not str
            or type(entry[1]) not in (int,float) or not isfinite(entry[1])
            or not lower_bpm <= entry[1] <= SETTINGS.maximum_bpm for entry in p.mastered):
        raise ValueError("Invalid recorded teaching tempo")
    exposure = decision.next_exposure
    if (decision.continuation in ("stop","pause")) != (exposure is None):
        raise ValueError("Teaching continuation/exposure mismatch")
    if event.kind == "manual" and event.manual is not None:
        manual = event.manual
        if manual.action == "select_step" and p.position != manual.number-1:
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

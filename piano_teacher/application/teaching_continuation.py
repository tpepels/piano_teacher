"""Exact destination readiness, asset reservation and one musical schedule.

This collaborator owns mechanical continuation. It never calls a generator,
LearningPlan navigation, or the engine; mode/session owners execute its effects.
"""
from dataclasses import dataclass, replace
from ..teaching_course import steps
from .score_artifacts import ScoreSelection
from .transport_commands import scheduled_offscreen_start


@dataclass(frozen=True, slots=True)
class TeachingSchedule:
    decision_id: str
    exposure: object
    run_at: float
    generation: int


@dataclass(frozen=True, slots=True)
class ContinuationReadiness:
    acknowledged: tuple | None
    revision: int
    fingerprint: str
    visual_beat: float
    outgoing_bpm: float
    reported_failure: tuple | None = None
    prepared_on_time: bool = False


@dataclass(frozen=True, slots=True)
class ContinuationEffect:
    action: str
    message: str = ""
    deadline: float | None = None
    count_in: float | None = None


class UnpreparedNextStage(RuntimeError):
    """A prepared source changed before atomic settlement completed."""


class TeachingContinuation:
    def __init__(self, future_score, transport):
        self.future_score = future_score
        self.transport = transport
        self.acknowledged = None
        self.reservation = None
        self.handoff_world = None
        self.schedule = None
        self.generation = 0

    @staticmethod
    def selection(pending, *, revision, fingerprint):
        if pending is None or pending.receipt is not None:
            return None
        decision = pending.decision
        exposure = decision.next_exposure
        if exposure is None or exposure.stage_key == pending.state.binding.stage_key:
            return None
        course = replace(pending.state.course,definition=decision.definition_after,progress=decision.progress_after)
        number = next(i+1 for i, step in enumerate(steps(course)) if step[3] == course.key)
        return ScoreSelection(piece=course.piece,phrase=course.stage.variant.phrase,hand=course.hand,
            stage_key=course.key,revision=revision+1,fingerprint=fingerprint,
            transformed_rhythm=course.stage.transformed_rhythm,display_name=str(course.stage.display_name or "")),number

    def prepare(self, pending, *, revision, fingerprint):
        selected = self.selection(pending,revision=revision,fingerprint=fingerprint)
        if selected is not None:
            selection,number = selected
            self.future_score.ensure(selection,number=number,label=selection.display_name)
        return selected

    def announce(self, pending, *, deadline):
        exposure = pending.decision.next_exposure
        if exposure is None:
            raise ValueError("Cannot announce a stopped teaching decision")
        if self.schedule is not None and self.schedule.decision_id == pending.decision.decision_id:
            if self.schedule.exposure != exposure:
                raise ValueError("Announced teaching exposure changed")
            if self.schedule.run_at != deadline:
                self.generation += 1
        self.schedule = TeachingSchedule(pending.decision.decision_id,exposure,deadline,self.generation)
        self.transport.announce_continuation(exposure.from_beat,deadline,exposure.bpm)

    def validate_announcement(self, pending):
        if self.schedule is None or self.schedule.decision_id != pending.decision.decision_id:
            return
        expected = (self.schedule.exposure.from_beat,self.schedule.run_at,self.schedule.exposure.bpm)
        if self.schedule.exposure != pending.decision.next_exposure or self.transport.announced_continuation != expected:
            raise ValueError("Announced teaching schedule no longer matches the selected exposure")

    def advance(self, pending, *, now, readiness):
        selected = self.selection(pending,revision=readiness.revision,fingerprint=readiness.fingerprint)
        if selected is None:
            return ContinuationEffect("settle")
        selection,number = selected
        accepted = readiness.acknowledged == (selection.stage_key,selection.revision)
        prebuilt = self.future_score.adopt(selection) if accepted and self.future_score.ready(selection) else None
        if prebuilt is None:
            self.reservation = None
            failure = self.future_score.failure(selection)
            reported = readiness.reported_failure
            if reported is not None and reported[:4] == (readiness.fingerprint,selection.revision,selection.stage_key,number):
                failure = failure or reported[4]
            if accepted and self.future_score.ready(selection):
                failure = failure or "Prepared stage assets were lost"
            if failure is not None:
                self.transport.pause(at=now)
                self.transport.next_at = 0.
                return ContinuationEffect("fault",failure)
            self.handoff_world = None
            self.transport.next_at = now+.10
            return ContinuationEffect("await","Preparing the next lesson while scrolling")
        self.reservation = (selection.identity,prebuilt)
        if self.handoff_world is None and not readiness.prepared_on_time:
            self.handoff_world = readiness.visual_beat+2.
            self.transport.next_at = now+2.*60./readiness.outgoing_bpm
            return ContinuationEffect("await")
        return ContinuationEffect("settle")

    @staticmethod
    def handoff(*, now, deadline, lead_beats, clear_beats, count_in_beats, bpm, rest_take_end, latency):
        rest_lead = (clear_beats or 0.)+lead_beats
        if clear_beats is not None:
            lead_beats = max(lead_beats,count_in_beats)+latency*bpm/60.
        next_deadline = scheduled_offscreen_start(max(deadline,now),lead_beats,bpm)
        if clear_beats is not None and rest_take_end is not None:
            take_end,rest_bpm = rest_take_end
            remaining = rest_lead-max(0.,now-take_end)*rest_bpm/60.
            next_deadline = now+max(max(0.,remaining)*60./bpm,latency+count_in_beats*60./bpm)
        return ContinuationEffect("start",deadline=next_deadline,count_in=min(lead_beats,count_in_beats))

    @staticmethod
    def after_settlement(decision, *, score_changed, prepared):
        if decision.continuation in ("stop","pause"):
            return ContinuationEffect("stop")
        if prepared:
            return ContinuationEffect("handoff")
        if decision.response is not None:
            return ContinuationEffect("response")
        if decision.remediation is not None:
            return ContinuationEffect("remediation")
        if decision.next_exposure is not None and decision.next_exposure.mode == "learn":
            return ContinuationEffect("guided")
        return ContinuationEffect("await_score" if score_changed else "continue")

    def capture_state(self):
        return (self.acknowledged,self.reservation,self.handoff_world,self.schedule,self.generation)

    def restore_state(self, snapshot):
        self.acknowledged,self.reservation,self.handoff_world,self.schedule,self.generation = snapshot

    def validate_reservation(self, pending):
        if self.reservation is None:
            return
        identity,assets = self.reservation
        exposure = pending.decision.next_exposure
        if (exposure is None or assets is None or self.acknowledged is None
                or self.acknowledged != (identity[2],identity[5])
                or exposure.stage_key != identity[2] or exposure.hand != identity[3]
                or pending.state.binding.fingerprint != identity[1]):
            raise UnpreparedNextStage("The next lesson score changed during settlement")

    def cancel(self, *, generation=None):
        self.reservation = self.handoff_world = self.schedule = None
        self.generation = self.generation+1 if generation is None else generation

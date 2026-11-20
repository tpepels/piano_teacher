"""Exact destination readiness, asset reservation and one musical schedule.

This collaborator owns mechanical continuation. It never calls a generator,
LearningPlan navigation, or the engine; mode/session owners execute its effects.
"""
from dataclasses import dataclass, replace
from ..teaching_course import steps, manual_progress
from .score_artifacts import ScoreSelection


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
    reported_failure: tuple | None = None


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
        self.native_failure: tuple | None = None
        self.prepared_published = False
        self.reservation = None
        self.schedule = None
        self.generation = 0

    def choose_ahead(self, plan, *, fingerprint: str, revision: int,
                     offset: int = 1, decided=None):
        """Select an exact future source without changing the active cursor."""
        if decided is not None and offset == 1:
            return decided
        number = plan.lesson_step_number + offset
        if number > len(plan.lesson_steps):
            return None
        future = manual_progress(
            plan.course_state(),"select_step",number=number)
        return ScoreSelection(
            piece=future.piece,phrase=future.stage.variant.phrase,
            hand=future.hand,stage_key=future.key,revision=revision+offset,
            fingerprint=fingerprint,
            transformed_rhythm=future.stage.transformed_rhythm,
            display_name=str(future.stage.display_name or "")),number

    @staticmethod
    def stage_label(step, display_name: str = "") -> str:
        hand = {"right":"Right hand","left":"Left hand",
                "both":"Both hands"}.get(step.hand,step.hand.capitalize())
        return f'{hand} · {display_name or "Next exercise"}'

    def ensure_next(self, planned) -> bytes:
        if planned is None:
            return b'{"status":"none"}'
        selection,number = planned
        return self.future_score.ensure(
            selection,number=number,
            label=self.stage_label(selection,selection.display_name))

    def report_native_failure(self, planned, *, fingerprint: str,
                              step_number: int, revision: int, error: str) -> dict:
        if planned is None:
            return {"accepted":False}
        selection,number = planned
        if (fingerprint != selection.fingerprint or number != step_number
                or selection.revision != revision):
            return {"accepted":False}
        message = str(error).strip()[:400] or "Native score compilation failed"
        self.native_failure = (
            fingerprint,revision,selection.stage_key,number,message)
        return {"accepted":True,"revision":revision,"step_number":number}

    def acknowledge_stage(self, planned, *, stage_key: str,
                          revision: int) -> dict:
        if planned is None:
            raise ValueError("No next lesson step to preload")
        selection,number = planned
        if selection.stage_key != stage_key or selection.revision != revision:
            raise ValueError("Preloaded step no longer matches the active course")
        if not self.future_score.ready(selection):
            raise ValueError("Next lesson notation is not yet prepared")
        self.acknowledged = (stage_key,revision)
        return {"accepted":True,"step_number":number,
                "revision":revision,"stage_key":stage_key}

    def warm_more(self, planned) -> None:
        if planned is None:
            return
        selection,number = planned
        self.future_score.warm(
            selection,number=number,
            label=self.stage_label(selection,selection.display_name))

    @staticmethod
    def selection(pending, *, revision, fingerprint):
        if pending is None or pending.receipt is not None:
            return None
        decision = pending.decision
        exposure = decision.next_exposure
        if exposure is None or exposure.stage_key == pending.state.binding.stage_key:
            return None
        if pending.state.definition.generator_name == "practice-flow":
            # Practice flow: a new step opens with its own Listen/Free or a
            # fresh count-in and engraves its own score; nothing to prebuild.
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
        repeat = self.schedule is not None and self.schedule.decision_id == pending.decision.decision_id
        if repeat and self.schedule.exposure != exposure:
            raise ValueError("Announced teaching exposure changed")
        current = self.transport.announced_continuation
        reusable = (repeat and current is not None and
                    self.transport.announced_deadline(exposure.from_beat) is not None and
                    abs(current[0] - exposure.from_beat) <= 1e-7 and
                    abs(current[2] - exposure.bpm) <= 1e-7)
        if reusable:
            # Pause/Resume re-times an already-admitted immutable future take.
            # Publishing it again used to increment announce_serial and send
            # Godot a different plan_id for notes it already had on screen.
            self.transport.retime_announcement(deadline)
        else:
            # The old future copy was withdrawn or the decision changed.
            # Only a genuinely new admission may receive a new identity.
            self.transport.announce_continuation(
                exposure.from_beat, deadline, exposure.bpm)
        if repeat and self.schedule.run_at != deadline:
            self.generation += 1
        self.schedule = TeachingSchedule(
            pending.decision.decision_id, exposure, deadline, self.generation)

    def validate_announcement(self, pending):
        if self.schedule is None or self.schedule.decision_id != pending.decision.decision_id:
            return
        expected = (self.schedule.exposure.from_beat,self.schedule.run_at,self.schedule.exposure.bpm)
        if self.schedule.exposure != pending.decision.next_exposure:
            raise ValueError("Announced teaching exposure changed before settlement")
        actual = self.transport.announced_continuation
        if actual is None:
            # The renderer may withdraw a future suffix before settlement.
            # Finish the graded result, then grant a fresh full reading lead
            # through the single scheduler rather than faulting the lesson.
            self.schedule = None
            return
        if actual != expected:
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
            self.transport.next_at = now+.10
            return ContinuationEffect("await","Preparing the next lesson while scrolling")
        self.reservation = (selection.identity,prebuilt)
        return ContinuationEffect("settle")

    @staticmethod
    def after_settlement(decision, *, score_changed, prepared):
        if decision.continuation in ("stop","pause"):
            return ContinuationEffect("stop")
        if decision.next_exposure is not None and decision.next_exposure.mode == "learn":
            # A preloaded score cannot skip a selected untimed guided lesson.
            return ContinuationEffect("guided")
        if prepared:
            return ContinuationEffect("handoff")
        if decision.response is not None:
            return ContinuationEffect("response")
        if decision.remediation is not None:
            return ContinuationEffect("remediation")
        return ContinuationEffect("await_score" if score_changed else "continue")

    def apply_settled_effect(self, decision, *, score_changed: bool,
                            stage_key: str, revision: int) -> ContinuationEffect:
        """Consume exact preloaded-stage identity once when grading commits."""
        prepared = (self.prepared_published and
                    self.acknowledged == (stage_key,revision))
        effect = self.after_settlement(
            decision,score_changed=score_changed,prepared=prepared)
        self.prepared_published = False
        if effect.action == "handoff":
            self.acknowledged = None
        return effect

    def capture_state(self):
        return (self.acknowledged,self.reservation,self.schedule,self.generation)

    def restore_state(self, snapshot):
        self.acknowledged,self.reservation,self.schedule,self.generation = snapshot

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
        self.reservation = self.schedule = None
        self.generation = self.generation+1 if generation is None else generation

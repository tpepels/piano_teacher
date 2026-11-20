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


@dataclass(frozen=True, slots=True)
class FeedbackWaiting:
    message: str = ""


@dataclass(frozen=True, slots=True)
class FeedbackFault:
    feedback: str
    next_action: str
    pause: bool = False
    stop_automatic: bool = False


@dataclass(frozen=True, slots=True)
class FeedbackTransaction:
    pending: object
    decision_id: str
    deadline: float
    source_revision: int


@dataclass(frozen=True, slots=True)
class ContinuationIdentity:
    decision_id: str
    fingerprint: str
    stage_key: str
    revision: int


@dataclass(frozen=True, slots=True)
class HandoffScore:
    identity: ContinuationIdentity
    exposure: object
    earliest_deadline: float
    count_in_beats: float
    bpm: float


@dataclass(frozen=True, slots=True)
class EnterSelectedExposure:
    identity: ContinuationIdentity
    exposure: object


@dataclass(frozen=True, slots=True)
class ApplySelectedResponse:
    identity: ContinuationIdentity
    response: object
    exposure: object
    deadline: float


@dataclass(frozen=True, slots=True)
class EnterSelectedRemediation:
    identity: ContinuationIdentity
    assignment: object
    exposure: object
    deadline: float


@dataclass(frozen=True, slots=True)
class AwaitSelectedScore:
    identity: ContinuationIdentity


@dataclass(frozen=True, slots=True)
class ContinueSelectedScore:
    identity: ContinuationIdentity
    exposure: object
    deadline: float
    bpm: float


@dataclass(frozen=True, slots=True)
class StopSelectedContinuation:
    identity: ContinuationIdentity
    message: str


SettledEffect = (HandoffScore | EnterSelectedExposure | ApplySelectedResponse |
    EnterSelectedRemediation | AwaitSelectedScore | ContinueSelectedScore |
    StopSelectedContinuation)


@dataclass(frozen=True, slots=True)
class SettledSourceFacts:
    fingerprint: str
    stage_key: str
    revision: int
    now: float
    bpm: float
    presentation_bpm: float
    count_in_beats: float
    automatic: bool
    flow_active: bool


@dataclass(frozen=True, slots=True)
class SettledPublication:
    effect: SettledEffect
    flow_outcome: object | None
    message: str


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
        self._readiness_poll_at = 0.0
        self._feedback_transaction: FeedbackTransaction | None = None
        self._settled_publication: SettledPublication | None = None

    def begin_feedback(self, pending, *, now: float, automatic: bool,
                       force_early: bool, revision: int, fingerprint: str
                       ) -> FeedbackWaiting | FeedbackFault | FeedbackTransaction:
        if (not automatic or not self.transport.next_at or pending is None
                or not (force_early or now >= self.transport.next_at)):
            return FeedbackWaiting()
        if self._feedback_transaction is not None:
            if self._feedback_transaction.pending is pending:
                return self._feedback_transaction
            raise ValueError("Another selected decision owns feedback publication")
        effect = self.advance(pending,now=now,
            readiness=self.readiness(revision=revision,fingerprint=fingerprint))
        if effect.action == "fault":
            return FeedbackFault("Cannot prepare the next lesson score",
                f"{effect.message}. Select another step or reopen the piece.",pause=True)
        if effect.action == "await":
            return FeedbackWaiting(effect.message)
        self._feedback_transaction = FeedbackTransaction(pending,
            pending.decision.decision_id,self.transport.next_at,revision)
        return self._feedback_transaction

    @staticmethod
    def settlement_failure(error: Exception) -> FeedbackFault:
        if isinstance(error,UnpreparedNextStage):
            return FeedbackFault("The next lesson score changed during grading",
                f"{error}. Select another step or reopen the piece.",pause=True)
        return FeedbackFault("Could not save the assessment",
            "Check storage or lesson generation, then Retry the attempt.",stop_automatic=True)

    def readiness(self, *, revision: int, fingerprint: str) -> ContinuationReadiness:
        return ContinuationReadiness(self.acknowledged,revision,fingerprint,self.native_failure)

    def decision_assets_ready(self, pending, *, revision: int, fingerprint: str) -> bool:
        planned = self.selection(pending,revision=revision,fingerprint=fingerprint)
        if planned is None:
            return False
        selection,_ = planned
        return (self.acknowledged == (selection.stage_key,selection.revision)
                and self.future_score.ready(selection))

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
        self._readiness_poll_at = 0.0
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
        if now < self._readiness_poll_at:
            return ContinuationEffect("await")
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
                return ContinuationEffect("fault",failure)
            # Retry only the asset lookup. Readiness cannot retime the
            # announced musical deadline or schedule the next take.
            self._readiness_poll_at = now+.10
            return ContinuationEffect("await","Preparing the next lesson while scrolling")
        self._readiness_poll_at = 0.0
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

    def finish_feedback(self, transaction: FeedbackTransaction,
                        facts: SettledSourceFacts) -> SettledPublication:
        """Publish one exact source effect after its durable selected decision."""
        if self._feedback_transaction is not transaction:
            raise ValueError("Feedback transaction is no longer current")
        identity = ContinuationIdentity(transaction.decision_id,facts.fingerprint,
            facts.stage_key,facts.revision)
        committed = transaction.pending.publication
        if committed is None:
            raise ValueError("Feedback continuation was not durably committed")
        selected = committed.selection
        binding = transaction.pending.state.binding
        expected = (binding.fingerprint,
            selected.stage_key if selected is not None else binding.stage_key,
            selected.revision if selected is not None else committed.source_revision)
        if (facts.fingerprint,facts.stage_key,facts.revision) != expected:
            raise ValueError("Feedback publication no longer matches its committed source")
        if self._settled_publication is not None:
            if self._settled_publication.effect.identity != identity:
                raise ValueError("The committed continuation source changed during publication")
            return self._settled_publication
        decision = transaction.pending.decision
        prepared = self.prepared_published and self.acknowledged == (
            facts.stage_key,facts.revision)
        chosen = self.after_settlement(decision,
            score_changed=facts.revision != transaction.source_revision,prepared=prepared)
        self.prepared_published = False
        if chosen.action == "handoff":
            self.acknowledged = None
        route = chosen.action
        if route == "guided":
            route = ("remediation" if decision.remediation is not None else
                "response" if decision.response is not None and decision.response.guided else
                "exposure")
        exposure = decision.next_exposure
        if route == "handoff":
            effect = HandoffScore(identity,exposure,transaction.deadline,
                facts.count_in_beats,facts.bpm)
        elif route == "exposure":
            effect = EnterSelectedExposure(identity,exposure)
        elif route == "response" and decision.response is not None and exposure is not None and facts.automatic:
            effect = ApplySelectedResponse(identity,decision.response,exposure,transaction.deadline)
        elif route == "remediation":
            effect = EnterSelectedRemediation(identity,decision.remediation,exposure,transaction.deadline)
        elif route == "await_score":
            effect = AwaitSelectedScore(identity)
        elif route == "continue":
            effect = ContinueSelectedScore(identity,exposure,transaction.deadline,facts.presentation_bpm)
        else:
            effect = StopSelectedContinuation(identity,decision.message)
        self._settled_publication = SettledPublication(effect,
            decision.flow_outcome if facts.flow_active else None,decision.message)
        return self._settled_publication

    def capture_state(self):
        return (self.acknowledged,self.reservation,self.schedule,self.generation)

    def restore_state(self, snapshot):
        self.acknowledged,self.reservation,self.schedule,self.generation = snapshot

    def reserved_asset(self, pending, *, changed: bool,
                       revision: int, fingerprint: str):
        """Check the exact decided successor before durable settlement.

        No score or reservation is consumed while the SQLite transaction
        can still fail and leave the original source active.
        """
        if not changed or self.reservation is None:
            return None
        planned = self.selection(pending,revision=revision,fingerprint=fingerprint)
        if planned is None:
            raise UnpreparedNextStage(
                "The decided lesson no longer has a preloaded next source")
        selection,_ = planned
        if (self.acknowledged != (selection.stage_key,selection.revision)
                or self.reservation[0] != selection.identity):
            raise UnpreparedNextStage(
                "The decided lesson selected a different next score")
        prepared = self.reservation[1]
        if prepared is None:
            raise UnpreparedNextStage(
                "The next lesson score changed after preloading")
        return prepared

    def consume_committed_asset(self, prepared, *, changed: bool,
                                auto: bool, selection):
        """One post-transaction owner for adopted/preloaded score identity."""
        self.prepared_published = False
        try:
            if not changed:
                return None
            if (prepared is None and auto and selection is not None
                    and self.acknowledged ==
                        (selection.stage_key,selection.revision)):
                prepared = self.future_score.adopt(selection)
            self.prepared_published = prepared is not None
            return prepared
        finally:
            self.reservation = None

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
        self._feedback_transaction = None
        self._settled_publication = None
        self.reservation = self.schedule = None
        self._readiness_poll_at = 0.0
        self.generation = self.generation+1 if generation is None else generation

    def stop(self) -> None:
        self.cancel()
        self.prepared_published = False
        self.native_failure = None

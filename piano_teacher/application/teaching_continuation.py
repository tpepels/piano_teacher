"""The settled continuation of a take and its one musical schedule.

This collaborator owns mechanical continuation. It never calls a generator,
LearningPlan navigation, or the engine; mode/session owners execute its effects.
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TeachingSchedule:
    decision_id: str
    exposure: object
    generation: int


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
    source_revision: int


@dataclass(frozen=True, slots=True)
class ContinuationIdentity:
    decision_id: str
    fingerprint: str
    stage_key: str
    revision: int


@dataclass(frozen=True, slots=True)
class EnterSelectedExposure:
    identity: ContinuationIdentity
    exposure: object


@dataclass(frozen=True, slots=True)
class EnterSelectedRemediation:
    identity: ContinuationIdentity
    assignment: object
    exposure: object


@dataclass(frozen=True, slots=True)
class AwaitSelectedScore:
    identity: ContinuationIdentity


@dataclass(frozen=True, slots=True)
class ContinueSelectedScore:
    identity: ContinuationIdentity
    exposure: object
    bpm: float


@dataclass(frozen=True, slots=True)
class StopSelectedContinuation:
    identity: ContinuationIdentity
    message: str


SettledEffect = (EnterSelectedExposure |
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


@dataclass(frozen=True, slots=True)
class SettledPublication:
    effect: SettledEffect
    flow_outcome: object | None
    message: str


class UnpreparedNextStage(RuntimeError):
    """A prepared source changed before atomic settlement completed."""


class TeachingContinuation:
    def __init__(self, transport):
        self.transport = transport
        self.schedule = None
        self.generation = 0
        self._feedback_transaction: FeedbackTransaction | None = None
        self._settled_publication: SettledPublication | None = None

    def begin_feedback(self, pending, *, now: float, automatic: bool,
                       revision: int, fingerprint: str
                       ) -> FeedbackWaiting | FeedbackFault | FeedbackTransaction:
        # An already selected continuation is bound to its original
        # transaction and durable receipt. A failed post-commit physical
        # effect may have stopped automatic playback or withdrawn the old
        # deadline; explicit Retry must still reach this exact transaction.
        if self._feedback_transaction is not None:
            if self._feedback_transaction.pending is pending:
                return self._feedback_transaction
            raise ValueError("Another selected decision owns feedback publication")
        if not automatic or not self.transport.continuation_pending or pending is None:
            return FeedbackWaiting()
        self._feedback_transaction = FeedbackTransaction(pending,
            pending.decision.decision_id,revision)
        return self._feedback_transaction

    @staticmethod
    def settlement_failure(error: Exception) -> FeedbackFault:
        if isinstance(error,UnpreparedNextStage):
            return FeedbackFault("The next lesson score changed during grading",
                f"{error}. Select another step or reopen the piece.",pause=True)
        return FeedbackFault("Could not save this result",
            "Check storage, then press Play to play the take again.",stop_automatic=True)

    def announce(self, pending):
        """Record the selected repeat; the musical timeline places it."""
        exposure = pending.decision.next_exposure
        if exposure is None:
            raise ValueError("Cannot announce a stopped teaching decision")
        repeat = self.schedule is not None and self.schedule.decision_id == pending.decision.decision_id
        if repeat and self.schedule.exposure != exposure:
            raise ValueError("Announced teaching exposure changed")
        self.schedule = TeachingSchedule(pending.decision.decision_id, exposure, self.generation)

    def validate_announcement(self, pending):
        if self.schedule is None or self.schedule.decision_id != pending.decision.decision_id:
            return
        if self.schedule.exposure != pending.decision.next_exposure:
            raise ValueError("Announced teaching exposure changed before settlement")

    @staticmethod
    def after_settlement(decision, *, score_changed) -> str:
        if decision.continuation in ("stop","pause"):
            return "stop"
        if decision.next_exposure is not None and decision.next_exposure.mode == "learn":
            return "guided"
        if decision.remediation is not None:
            return "remediation"
        return "await_score" if score_changed else "continue"

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
        route = self.after_settlement(decision,
            score_changed=facts.revision != transaction.source_revision)
        if route == "guided":
            route = "remediation" if decision.remediation is not None else "exposure"
        exposure = decision.next_exposure
        if route == "exposure":
            effect = EnterSelectedExposure(identity,exposure)
        elif route == "remediation":
            effect = EnterSelectedRemediation(identity,decision.remediation,exposure)
        elif route == "await_score":
            effect = AwaitSelectedScore(identity)
        elif route == "continue":
            effect = ContinueSelectedScore(identity,exposure,facts.presentation_bpm)
        else:
            effect = StopSelectedContinuation(identity,decision.message)
        self._settled_publication = SettledPublication(effect,
            decision.flow_outcome,decision.message)
        return self._settled_publication

    def capture_state(self):
        return (self.schedule,self.generation)

    def restore_state(self, snapshot):
        self.schedule,self.generation = snapshot

    def cancel(self, *, generation=None):
        self._feedback_transaction = None
        self._settled_publication = None
        self.schedule = None
        self.generation = self.generation+1 if generation is None else generation

    def stop(self) -> None:
        self.cancel()

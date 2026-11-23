"""Decision lifetime and atomic evidence/progress installation.

This owner has no engine, transport or renderer reference. Preparation chooses
once; checkpoint and settlement apply only the recorded immutable effects.
"""
from __future__ import annotations
from dataclasses import dataclass, replace, asdict
from contextlib import contextmanager
from ..teaching_decisions import TeachingBinding, validate_teaching_decision
from .assessment_settlement import AssessedTake, assess_completed_take
from ..completion_route import completion_route, completion_effect, CompletionEffect
from typing import Callable, Sequence
from ..music import Phrase
from ..practice import Assessment, PlayedNote
from ..exercise_contracts import TempoMap
from .practice_assessment import PracticeAssessmentPolicies
from .score_artifacts import ScoreSelection


@dataclass(slots=True)
class PendingTeachingDecision:
    event: object
    state: object
    decision: object
    checkpoint_progress: object = None
    phase: str = "decided"
    receipt: object = None
    publication: object = None

    @property
    def assessment(self):
        return self.event.assessment


@dataclass(frozen=True, slots=True)
class SettlementReceipt:
    decision: object
    previous_stage: str
    previous_bpm: float
    stage_changed: bool
    accelerated: bool
    source_changed: bool

    @property
    def message(self):
        return self.decision.message


@dataclass(frozen=True, slots=True)
class CommittedAttempt:
    receipt: SettlementReceipt
    selection: ScoreSelection | None
    prepared: object
    source_revision: int
    previous_duration: float
    previous_visual_offset: float
    committed_at: float


@dataclass(frozen=True, slots=True)
class TakeResult:
    """The exact graded source/take and recorded physical note evidence.

    TeachingBinding retains run/session, source fingerprint, original
    stage, transport, course/authority and cancellation identities.
    Recorded PlayedNotes are frozen, retaining press ID, attack time,
    release time and ambiguous key-pairing evidence. Assessment notes
    retain original imported source-note IDs and timing measurements.
    """
    binding: TeachingBinding
    score_revision: int
    attempt_id: str | None
    mode: str
    hand: str
    from_beat: float
    end_beat: float
    bpm: float
    played: tuple[PlayedNote, ...]
    assessment: Assessment
    source_note_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompletedTake:
    assessed: AssessedTake
    route: str
    summary: dict
    pending: object
    settled: bool
    effect: CompletionEffect
    take: TakeResult


@dataclass(frozen=True, slots=True)
class PendingFullCompletion:
    pending: PendingTeachingDecision
    total_beats: float
    duration: float

    @property
    def result(self):
        return self.pending.assessment


class AttemptSettlement:
    def __init__(self, repository, capture, learner_progress):
        self.repository = repository
        self.capture = capture
        self.learner_progress = learner_progress
        self.pending = None
        self._completion = None
        self._full_completion: PendingFullCompletion | None = None
        # An effect may enter a selected successor via the ordinary source
        # installer, whose Stop/new-take cleanup must not discard the old
        # durable receipt until that effect has been fully acknowledged.
        self._publishing: PendingTeachingDecision | None = None
        self.authority_revision = 0
        self.course_revision = 0
        self.cancellation_generation = 0

    def prepare(self, *, event, state, generator):
        if self.pending is not None:
            if self.pending.event.event_id == event.event_id:
                if self.pending.event != event or self.pending.state != state:
                    raise ValueError("Conflicting pending teaching event")
                return self.pending
            # A different event must never overwrite a durable but not yet
            # published settlement. Stop/source replacement explicitly calls
            # cancel() and advances the cancellation epoch before new work.
            if (self.pending.receipt is not None
                    and self.pending.phase != "published"):
                raise ValueError("A committed teaching receipt awaits publication")
        decision = generator.decide_teaching(event, state)
        validate_teaching_decision(decision, event=event, state=state)
        pending = PendingTeachingDecision(event, state, decision)
        self.pending = pending
        return pending

    @property
    def pending_result(self):
        """The selected full result has one lifetime, through publication."""
        p = self.pending
        return (p.assessment if p is not None and
                p.event.kind == "full_result" and p.phase != "published" else None)

    @property
    def pending_assessed_bpm(self):
        return (self.pending.state.route.performed_bpm
                if self.pending_result is not None else None)

    @contextmanager
    def publishing(self, pending: PendingTeachingDecision):
        """Protect only the currently selected durable effect handoff.

        No lock or independent event worker is introduced. The outer
        PracticeSession lock serializes commands, MIDI and this effect.
        Internal new-exposure cleanup may advance the cancellation epoch
        but may not erase the receipt being published.
        """
        if (pending is not self.pending or pending.receipt is None
                or pending.phase != "effects_applied"
                or self._publishing is not None):
            raise ValueError("A committed source effect requires one publication lease")
        self._publishing = pending
        try:
            yield
        finally:
            self._publishing = None

    def finish_publication(self) -> None:
        """Publish only after the durable receipt's source effects completed.

        The state transition is one-way and idempotent. Callers cannot hide
        an unsettled or partially applied lesson decision by marking it
        published before the already-selected continuation is installed.
        """
        pending = self.pending
        if pending is None or pending.phase == "published":
            return
        if (pending.phase != "effects_applied"
                or pending.receipt is None or pending.publication is None):
            raise ValueError("Cannot publish a teaching decision before its source effects")
        pending.phase = "published"

    def effects_applied(self, pending: PendingTeachingDecision) -> None:
        """Acknowledge post-commit source effects exactly once per receipt.

        Durably settled progress can outlive a failed next-step handoff.
        The following retry must not adopt the same stage, rewind or reset
        transport presentation twice; only the continuation remains pending.
        """
        if pending is not self.pending or pending.receipt is None or pending.publication is None:
            raise ValueError("Post-commit effects require the current durable receipt")
        if pending.phase == "settled":
            pending.phase = "effects_applied"
        elif pending.phase not in ("effects_applied", "published"):
            raise ValueError("Cannot apply effects to an unsettled teaching decision")

    @property
    def pending_full_completion(self) -> PendingFullCompletion | None:
        return self._full_completion

    @property
    def feedback_pending(self) -> bool:
        return self.pending_result is not None or self._full_completion is not None

    def begin_full_completion(self, result, *, total_beats: float,
                              duration: float) -> PendingFullCompletion:
        pending = self.pending
        if pending is None or pending.assessment is not result:
            raise ValueError("Completed passage has no selected assessment")
        if self._full_completion is None:
            self._full_completion = PendingFullCompletion(pending,total_beats,duration)
        elif self._full_completion.pending is not pending:
            raise ValueError("Another selected passage owns completion publication")
        return self._full_completion

    def finish_full_completion(self, completed: PendingFullCompletion) -> None:
        # A successfully started successor cancels the old epoch itself.
        if self._full_completion is not None and self._full_completion is not completed:
            raise ValueError("Cannot finish another passage's publication")
        self._full_completion = None

    def command_applied(self) -> None:
        """Invalidate bindings after one accepted manual progress mutation."""
        self.authority_revision += 1

    def commit_full_passage(self, *, plan, binding, now: float,
                            continuation, score_revision: int,
                            visual_offset: float) -> CommittedAttempt:
        """Freeze successor publication before committing any progress.

        A failed post-commit publication retries this same receipt, source
        revision and offset. It cannot grade again, select a second exposure
        or increment the revision twice because the plan already advanced.
        """
        pending = self.pending
        if pending.publication is not None:
            committed = pending.publication
            original = pending.state.binding
            expected_piece = (committed.selection.piece if committed.selection
                              else pending.state.course.piece)
            expected_stage = (committed.selection.stage_key if committed.selection
                              else original.stage_key)
            # A committed result can be replayed after a failed physical
            # adoption, but it cannot be claimed by another run, learner,
            # course epoch or cancellation. The lesson progress was already
            # installed by the durable transaction and must still be exact.
            if (binding.run_id != original.run_id
                    or binding.session_id != original.session_id
                    or binding.fingerprint != original.fingerprint
                    or binding.transport_id != original.transport_id
                    or binding.cancellation_generation != original.cancellation_generation
                    or binding.authority_revision != original.authority_revision + 1
                    or binding.course_revision != original.course_revision
                        + int(committed.receipt.source_changed)
                    or binding.stage_key != expected_stage
                    or plan.piece is not expected_piece
                    or plan.teaching_progress() != pending.decision.progress_after
                    or score_revision not in (committed.source_revision,
                        committed.selection.revision if committed.selection
                        else committed.source_revision)):
                raise ValueError("Committed source changed before publication")
            return committed
        continuation.validate_announcement(pending)
        decision, state = pending.decision,pending.state
        chosen = replace(state.course,definition=decision.definition_after,
                         progress=decision.progress_after)
        changed = chosen.key != state.binding.stage_key
        selection = (ScoreSelection(
            piece=chosen.piece,phrase=chosen.stage.variant.phrase,
            hand=chosen.hand,stage_key=chosen.key,revision=score_revision+1,
            fingerprint=state.binding.fingerprint,
            transformed_rhythm=chosen.stage.transformed_rhythm,
            display_name=str(chosen.stage.display_name or "")) if changed else None)
        prepared = continuation.reserved_asset(
            pending,changed=changed,revision=score_revision,
            fingerprint=state.binding.fingerprint)
        source = state.course.stage.variant.phrase
        duration = source.sounding_end-source.start
        outcome = self.settle(pending,plan=plan,binding=binding,now=now,
                              continuation=continuation)
        pending.publication = CommittedAttempt(
            outcome,selection,prepared,score_revision,duration,visual_offset,now)
        return pending.publication

    def complete_take(
        self, *, phrase: Phrase, hand: str, bpm: float,
        played: Sequence[PlayedNote], from_beat: float, end_beat: float,
        tempo: TempoMap | None, policies: PracticeAssessmentPolicies,
        layout_for_feedback: Callable[[], dict], mode: str,
        review_end_beat: float | None, automatic_remedial_review: bool,
        performance_review: Callable[[Phrase, Assessment], dict],
        prepare_decision: Callable, plan,
        binding: TeachingBinding, now: float,
        score_revision: int,
    ) -> CompletedTake:
        """One full/focused grading and evidence-settlement boundary.

        All routes use the same assessed notes and the same immutable decision;
        no progress, verdict or next exposure is reselected by the caller.
        Full-passage outcomes remain pending for their authorized successor
        boundary; focused/performance decisions settle immediately.
        """
        if self._completion is None:
            frozen_played = tuple(played)
            assessed = assess_completed_take(
                phrase=phrase,hand=hand,bpm=bpm,played=frozen_played,
                from_beat=from_beat,end_beat=end_beat,tempo=tempo,
                policies=policies,layout_for_feedback=layout_for_feedback)
            result = assessed.result
            route = completion_route(mode,review_end_beat,from_beat,
                full_from_beat=phrase.first_attack_beat)
            if automatic_remedial_review and route == "section_review":
                route = "partial_recovery"
            summary = performance_review(phrase,result)
            if route == "full_passage":
                pending = prepare_decision("full_result",result)
            else:
                pending = prepare_decision("focused_result",result,end_beat=end_beat)
            take = TakeResult(
                binding=binding, score_revision=score_revision,
                attempt_id=pending.event.attempt_id, mode=mode,
                hand=hand, from_beat=from_beat, end_beat=end_beat,
                bpm=bpm, played=frozen_played, assessment=result,
                source_note_ids=tuple(
                    entry.note.source_id for entry in result.notes))
            self._completion = CompletedTake(
                assessed,route,summary,pending,False,
                completion_effect(route,pending.decision),take)
        completed = self._completion
        take = completed.take
        # Focused/performance outcomes may advance the lesson as part of
        # their immediate durable settlement. A later presentation failure
        # must reuse that receipt rather than compare against the already
        # advanced original teaching binding or re-seal the same evidence.
        pending = completed.pending
        if pending.receipt is not None and completed.route != "full_passage":
            chosen = replace(pending.state.course,
                definition=pending.decision.definition_after,
                progress=pending.decision.progress_after)
            # These arguments now describe the selected successor rather
            # than the original graded take. Replay only its frozen receipt,
            # and validate the installed, already-committed lesson instead.
            if (pending is not self.pending
                    or score_revision not in (
                        take.score_revision,
                        take.score_revision + int(pending.receipt.stage_changed))
                    or plan.piece is not pending.state.course.piece
                    or plan.lesson_definition != pending.decision.definition_after
                    or binding.run_id != take.binding.run_id
                    or binding.session_id != take.binding.session_id
                    or binding.fingerprint != take.binding.fingerprint
                    or binding.transport_id != take.binding.transport_id
                    or binding.cancellation_generation != take.binding.cancellation_generation
                    or binding.authority_revision != take.binding.authority_revision + 1
                    or binding.course_revision != (
                        take.binding.course_revision + int(pending.receipt.source_changed))
                    or plan.teaching_progress() != pending.decision.progress_after
                    or binding.stage_key != chosen.key):
                raise ValueError("Committed focused take changed before publication retry")
            self._completion = replace(completed,settled=True)
            return self._completion
        if (binding != take.binding or score_revision != take.score_revision
                or hand != take.hand or mode != take.mode or bpm != take.bpm
                or from_beat != take.from_beat or end_beat != take.end_beat):
            raise ValueError(
                "Completed take source or window changed before evidence settlement")
        assessed,route,summary,pending = (
            completed.assessed,completed.route,completed.summary,
            completed.pending)
        result = assessed.result
        settled = self.seal_completed_take(
            pending,played=take.played,route=route,mode=take.mode,
            at_target=take.bpm >= plan.target_bpm,
            assessed_end_beat=take.end_beat,result=take.assessment,plan=plan,
            binding=binding,now=now,performance_summary=summary)
        self._completion = replace(completed,settled=settled)
        return self._completion

    def checkpoint_failed_streak(self, pending, *, plan, now):
        if not pending.decision.invalidate_failed_streak or pending.checkpoint_progress is not None:
            return
        expected = pending.decision.before_progress
        if plan.teaching_progress() != expected:
            raise ValueError("Stale failed-streak checkpoint progress")
        after = replace(expected, streak=0)
        before = plan.capture_teaching_state()
        try:
            with self.capture.atomic():
                plan.apply_teaching_progress(after, definition=pending.state.definition, expected=expected)
                if expected.streak:
                    self.repository.save(plan, pending.state.binding.fingerprint)
                    self.capture.event("failed_streak_invalidated", {"decision_id": pending.decision.decision_id},
                                       key=pending.event.event_id+":failed-streak")
        except BaseException:
            plan.restore_teaching_state(before)
            raise
        pending.checkpoint_progress = after

    def settle(self, pending, *, plan, binding, now, performance_summary=None, continuation=None):
        if pending is not self.pending:
            raise ValueError("Cannot settle a superseded teaching decision")
        if pending.receipt is not None:
            return pending.receipt
        decision, state, result = pending.decision, pending.state, pending.assessment
        if binding != decision.expected:
            raise ValueError("Stale teaching binding at settlement")
        if plan.lesson_definition != state.definition:
            raise ValueError("Teaching course changed before settlement")
        expected = pending.checkpoint_progress or decision.before_progress
        if plan.teaching_progress() != expected:
            raise ValueError("Stale teaching progress at settlement")
        before = plan.capture_teaching_state()
        continuation_before = continuation.capture_successor_state() if continuation is not None else None
        if continuation is not None:
            continuation.validate_reservation(pending)
        try:
            with self.capture.atomic():
                self.capture.decision({"version": 1, "trigger": pending.event.kind,
                    "policy": "practice-flow", "policy_version": "practice-flow",
                    "parameters": {},
                    "reason": decision.reason, "eligible": decision.mastery_eligible,
                    "before_stage": state.binding.stage_key,
                    "before_bpm": state.route.performed_bpm, "after_bpm": decision.progress_after.bpm,
                    "selected": asdict(decision.next_exposure) if decision.next_exposure else None,
                    "wrong_missed_source_ids": [n.note.source_id for n in result.notes if n.status in ("wrong","missed")] if result is not None else [],
                    "origin": "automatic", "state": "applied"}, decision_id=decision.decision_id)
                self.capture.persist()
                if pending.event.kind == "guided_completed" and pending.event.completed and not state.route.remediation_active:
                    from ..learner_state import guided_units
                    unit = next((unit for unit in guided_units(plan.active_variant,plan.piece.bar_boundaries)
                        if (unit["start_beat"],unit["end_beat"]) == state.route.guided_range),None)
                    self.learner_progress.record_guided_preparation(fingerprint=state.binding.fingerprint,
                        stage_key=state.binding.stage_key,unit=unit,assisted_count=pending.event.assisted_count)
                plan.apply_teaching_progress(decision.progress_after,
                    definition=decision.definition_after, expected=expected)
                if continuation is not None:
                    continuation.validate_reservation(pending)
                self.repository.save(plan, state.binding.fingerprint)
                if self.capture.attempt_id is not None:
                    self.capture.event("progression", {
                        "decision_id": decision.decision_id, "fingerprint": state.binding.fingerprint,
                        "before_stage": state.binding.stage_key, "after_stage": plan.identity,
                        "before_bpm": state.route.performed_bpm, "after_bpm": plan.bpm,
                        "streak": plan.streak,
                        "mastery_transition": state.binding.stage_key not in dict(state.progress.mastered)
                            and state.binding.stage_key in plan.mastered,
                        "mastery_bpm": plan.mastered.get(state.binding.stage_key)},
                        key=pending.event.event_id+":progression")
        except BaseException:
            plan.restore_teaching_state(before)
            if continuation is not None:
                continuation.restore_successor_state(continuation_before)
            raise
        changed = plan.identity != state.binding.stage_key
        receipt = SettlementReceipt(decision, state.binding.stage_key, state.route.performed_bpm,
            changed, not changed and plan.bpm > state.route.performed_bpm,
            decision.definition_after != state.definition)
        pending.receipt = receipt
        pending.phase = "settled"
        self.authority_revision += 1
        if receipt.source_changed:
            self.course_revision += 1
        self.capture.finish()
        return receipt

    def interrupt_current(self, *, reason: str, played=(),
                          censor: bool = True, extra=None,
                          now: float | None = None,
                          flush: bool = False) -> None:
        """Single transaction owner for stopping or replacing a take."""
        with self.capture.atomic():
            self.capture.interrupt(reason,played,censor=censor,extra=extra)
            if flush:
                self.capture.flush_intervals(now)

    def reset_piece_path(self, *, fingerprint: str, replacement,
                         played, now: float) -> None:
        """Reset the exact piece's progress with one savepoint."""
        with self.capture.atomic():
            self.capture.interrupt("lesson_reset",played)
            self.capture.flush_intervals(now)
            self.repository.reset_piece(fingerprint)
            self.repository.save(replacement,fingerprint)
            self.capture.event("lesson_reset",{
                "fingerprint":fingerprint,"preserves_history":True})

    def checkpoint(self, played, *, boundary: float) -> None:
        self.capture.checkpoint(played,boundary=boundary)

    def seal_guided_preparation(self, pending, *, guidance: dict,
                                plan, binding, now) -> None:
        """Atomically finish a completed guided attempt and its decision.

        The capture seal precedes the single idempotent settlement, matching
        the source-constrained evidence schema. On storage failure the engine
        preserves the same active exposure and may retry the same decision.
        """
        self.capture.seal(
            self.capture.guided.presses,state="completed",
            reason="guided_preparation",extra={"guidance":guidance})
        self.settle(pending,plan=plan,binding=binding,now=now)

    def seal_completed_take(self, pending, *, played, route: str,
                            mode: str, at_target: bool, assessed_end_beat: float,
                            result, plan, binding, now,
                            performance_summary=None) -> bool:
        """Single owner of end-of-take sealing and focused settlement.

        A full-passage decision deliberately remains pending until its
        announced next-stage boundary. A focused or performance review is
        settled immediately, against the same exact captured source/verdict.
        """
        self.capture.seal(
            played,state="completed",reason=route,result=result,
            verdict=pending.decision.verdict,
            eligible=(route=="full_passage" and mode=="practice"
                      and at_target),
            extra={"assessed_end_beat":assessed_end_beat})
        if route == "full_passage":
            return False
        self.settle(pending,plan=plan,binding=binding,now=now,
                    performance_summary=(
                        performance_summary if route == "perform" else None))
        return True

    def cancel(self, pending=None, *, reason, now):
        if pending is not None and pending is not self.pending:
            return
        # Only during a validated, serialized successor publication may
        # ordinary source-install/Stop cleanup retain an old receipt. This
        # prevents a new guided or timed exposure from erasing its durable
        # predecessor halfway through a successful handoff.
        keep_receipt = (self.pending is not None
                        and self._publishing is self.pending
                        and self.pending.phase == "effects_applied")
        if not keep_receipt:
            self.pending = None
        self._completion = None
        self._full_completion = None
        self.cancellation_generation += 1

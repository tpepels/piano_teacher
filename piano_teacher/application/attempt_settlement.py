"""Decision lifetime and atomic evidence/progress installation.

This owner has no engine, transport or renderer reference. Preparation chooses
once; checkpoint and settlement apply only the recorded immutable effects.
"""
from __future__ import annotations
from dataclasses import dataclass, replace, asdict
from ..teaching_decisions import TeachingBinding, validate_teaching_decision
from .mistake_responses import mistake_policy_facts
from .assessment_settlement import AssessedTake, assess_completed_take
from ..completion_route import completion_route, completion_effect, CompletionEffect
from typing import Callable, Sequence
from ..music import Phrase
from ..practice import Assessment, PlayedNote
from ..exercise_contracts import TempoMap
from .practice_assessment import PracticeAssessmentPolicies
from .score_artifacts import ScoreSelection
from .rolling_recovery import project_rolling_response


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
    response: object
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


@dataclass(frozen=True, slots=True)
class RollingTake:
    decision: object
    phrase: Phrase
    grid: tuple
    score_beat: float
    sampled_at: float
    pending: PendingTeachingDecision
    transition: object
    outgoing_bpm: float
    scored_end: float
    take: TakeResult


class AttemptSettlement:
    def __init__(self, repository, capture, source_feedback, learner_progress):
        self.repository = repository
        self.capture = capture
        self.source_feedback = source_feedback
        self.learner_progress = learner_progress
        self.pending = None
        self._completion = None
        self._full_completion: PendingFullCompletion | None = None
        self._rolling = None
        self.authority_revision = 0
        self.course_revision = 0
        self.cancellation_generation = 0

    def prepare(self, *, event, state, generator):
        if self.pending is not None and self.pending.event.event_id == event.event_id:
            if self.pending.event != event or self.pending.state != state:
                raise ValueError("Conflicting pending teaching event")
            return self.pending
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

    def finish_publication(self) -> None:
        if self.pending is not None:
            self.pending.phase = "published"

    def effects_applied(self, pending: PendingTeachingDecision) -> None:
        """Acknowledge post-commit source effects exactly once per receipt.

        Durably settled progress can outlive a failed next-step handoff.
        The following retry must not adopt the same stage, rewind or reset
        transport presentation twice; only the continuation remains pending.
        """
        if pending is not self.pending or pending.receipt is None or pending.publication is None:
            raise ValueError("Post-commit effects require the current durable receipt")
        if pending.phase not in ("effects_applied", "published"):
            pending.phase = "effects_applied"

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

    @property
    def pending_rolling(self):
        r = self._rolling
        return (r.decision,r.phrase,r.grid,r.score_beat,r.sampled_at) if r else None

    def finish_rolling_publication(self) -> None:
        self._rolling = None

    def complete_rolling(self, *, decision, phrase, grid, score_beat,
                         now, bpm, scored_end, hand, played, from_beat,
                         tempo, policies, prepare_decision, plan, binding,
                         policy, score_revision: int) -> RollingTake:
        """Retain original source/tempo facts through rolling storage retries."""
        if self._rolling is None:
            original_notes = tuple(played)
            assessed = policies.select(tempo).grade(
                phrase,hand=hand,bpm=bpm,played=original_notes,from_beat=from_beat,
                end_beat=decision.end_beat,tempo=tempo)
            pending = prepare_decision("rolling_result",assessed,
                rolling=decision,end_beat=decision.end_beat)
            response = pending.decision.response
            chosen = replace(pending.state.course,
                definition=pending.decision.definition_after,
                progress=pending.decision.progress_after)
            transition = (None if response.action == "continue" else
                project_rolling_response(response,decision,grid=grid,
                    first_bar=phrase.first_bar,
                    before_bpm=pending.state.route.performed_bpm,now=now,
                    same_stage=chosen.key == pending.state.binding.stage_key,
                    source_duration=phrase.end-phrase.start))
            take = TakeResult(
                binding=binding, score_revision=score_revision,
                attempt_id=pending.event.attempt_id, mode="practice",
                hand=hand, from_beat=from_beat, end_beat=decision.end_beat,
                bpm=bpm, played=original_notes, assessment=assessed,
                source_note_ids=tuple(
                    entry.note.source_id for entry in assessed.notes))
            self._rolling = RollingTake(decision,phrase,grid,score_beat,now,
                pending,transition,bpm,scored_end,take)
        completed = self._rolling
        take = completed.take
        # On a persistence retry use the original scored notes, not a
        # recorder mutated by a later MIDI note. After a durable receipt
        # the authority counter can advance, but the source/take identity
        # must still match before any presentation effect is replayed.
        if (score_revision != take.score_revision or
                binding.fingerprint != take.binding.fingerprint or
                binding.stage_key != take.binding.stage_key or
                binding.transport_id != take.binding.transport_id or
                binding.cancellation_generation != take.binding.cancellation_generation or
                hand != take.hand or bpm != take.bpm or
                from_beat != take.from_beat or
                decision.end_beat != take.end_beat or
                completed.phrase is not phrase):
            raise ValueError("Rolling take source or timing changed before settlement")
        if completed.pending.receipt is None and binding != take.binding:
            raise ValueError("Rolling take authority changed before durable settlement")
        if completed.transition is None:
            # No interruption and no durable assessment; keep recording the
            # same exposure, rather than leaving a selected stale decision.
            self.pending = None
            self._rolling = None
            return completed
        self.seal_rolling_recovery(
            completed.pending,played=take.played,
            result=take.assessment,end_beat=take.end_beat,
            plan=plan,binding=binding,now=now,policy=policy)
        return completed

    def commit_full_passage(self, *, plan, binding, now: float,
                            continuation, policy, score_revision: int,
                            visual_offset: float) -> CommittedAttempt:
        """Freeze successor publication before committing any progress.

        A failed post-commit publication retries this same receipt, source
        revision and offset. It cannot grade again, select a second exposure
        or increment the revision twice because the plan already advanced.
        """
        pending = self.pending
        if pending.publication is not None:
            committed = pending.publication
            expected_piece = (committed.selection.piece if committed.selection
                              else pending.state.course.piece)
            if (binding.fingerprint != pending.state.binding.fingerprint
                    or plan.piece is not expected_piece
                    or score_revision not in (committed.source_revision,
                        committed.selection.revision if committed.selection
                        else committed.source_revision)):
                raise ValueError("Committed source changed before publication")
            return committed
        continuation.validate_announcement(pending)
        if policy != pending.state.policy:
            raise ValueError("Teaching policy changed before settlement")
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
                              continuation=continuation,policy=policy)
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
        binding: TeachingBinding, now: float, policy,
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
                response = None
            else:
                pending = prepare_decision("focused_result",result,end_beat=end_beat)
                response = pending.decision.response
            take = TakeResult(
                binding=binding, score_revision=score_revision,
                attempt_id=pending.event.attempt_id, mode=mode,
                hand=hand, from_beat=from_beat, end_beat=end_beat,
                bpm=bpm, played=frozen_played, assessment=result,
                source_note_ids=tuple(
                    entry.note.source_id for entry in result.notes))
            self._completion = CompletedTake(
                assessed,route,summary,pending,response,False,
                completion_effect(route,pending.decision),take)
        completed = self._completion
        take = completed.take
        if (binding != take.binding or score_revision != take.score_revision
                or hand != take.hand or mode != take.mode or bpm != take.bpm
                or from_beat != take.from_beat or end_beat != take.end_beat):
            raise ValueError(
                "Completed take source or window changed before evidence settlement")
        assessed,route,summary,pending,response = (
            completed.assessed,completed.route,completed.summary,
            completed.pending,completed.response)
        result = assessed.result
        settled = self.seal_completed_take(
            pending,played=take.played,route=route,mode=take.mode,
            at_target=take.bpm >= plan.target_bpm,
            assessed_end_beat=take.end_beat,result=take.assessment,plan=plan,
            binding=binding,now=now,policy=policy,performance_summary=summary)
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

    def settle(self, pending, *, plan, binding, now, performance_summary=None, continuation=None, policy=None):
        if pending.receipt is not None:
            return pending.receipt
        decision, state, result = pending.decision, pending.state, pending.assessment
        if binding != decision.expected:
            raise ValueError("Stale teaching binding at settlement")
        if policy is not None and policy != state.policy:
            raise ValueError("Teaching policy changed before settlement")
        if plan.lesson_definition != state.definition:
            raise ValueError("Teaching course changed before settlement")
        expected = pending.checkpoint_progress or decision.before_progress
        if plan.teaching_progress() != expected:
            raise ValueError("Stale teaching progress at settlement")
        before = plan.capture_teaching_state()
        continuation_before = continuation.capture_state() if continuation is not None else None
        if continuation is not None:
            continuation.validate_reservation(pending)
        try:
            with self.capture.atomic():
                self.capture.decision({"version": 1, "trigger": pending.event.kind,
                    "policy": state.policy.name, "policy_version": state.policy.version,
                    "parameters": mistake_policy_facts(state.policy),
                    "reason": decision.reason, "eligible": decision.mastery_eligible,
                    "before_stage": state.binding.stage_key,
                    "before_bpm": state.route.performed_bpm, "after_bpm": decision.progress_after.bpm,
                    "selected": asdict(decision.response) if decision.response else asdict(decision.next_exposure) if decision.next_exposure else None,
                    "wrong_missed_source_ids": [n.note.source_id for n in result.notes if n.status in ("wrong","missed")] if result is not None else [],
                    "origin": "automatic", "state": "applied"}, decision_id=decision.decision_id)
                self.capture.persist()
                if result is not None and pending.event.kind == "full_result":
                    if (plan.accepts_performance_feedback and state.course.stage.variant.level == "original"
                            and not state.route.warmup and result.notes):
                        self.source_feedback.observe(state.binding.fingerprint, result)
                    if decision.verdict is not None and decision.verdict.clears_trouble:
                        self.learner_progress.resolve_trouble(
                            fingerprint=state.binding.fingerprint,
                            stage_key=state.binding.stage_key)
                if pending.event.kind == "guided_completed" and pending.event.completed and not state.route.remediation_active:
                    from ..learner_state import guided_units
                    unit = next((unit for unit in guided_units(plan.active_variant,plan.piece.bar_boundaries)
                        if (unit["start_beat"],unit["end_beat"]) == state.route.guided_range),None)
                    self.learner_progress.record_guided_preparation(fingerprint=state.binding.fingerprint,
                        stage_key=state.binding.stage_key,unit=unit,assisted_count=pending.event.assisted_count)
                if pending.event.kind == "rolling_result" and state.binding.fingerprint:
                    from ..learner_state import guided_units
                    rolling = pending.event.rolling
                    unit = next((unit for unit in guided_units(plan.active_variant, plan.piece.bar_boundaries)
                        if unit["start_beat"] == rolling.restart_beat and unit["end_beat"] == rolling.end_beat), None)
                    if unit is not None:
                        self.learner_progress.record_rolling_trouble(fingerprint=state.binding.fingerprint,
                            stage_key=state.binding.stage_key, unit=unit, assessed_notes=result.notes,
                            phrase_start=state.course.stage.variant.phrase.start)
                if performance_summary is not None and state.binding.fingerprint:
                    if (decision.verdict is not None
                            and decision.verdict.clears_trouble):
                        self.learner_progress.resolve_trouble(
                            fingerprint=state.binding.fingerprint,
                            stage_key=state.binding.stage_key)
                    else:
                        for unit in performance_summary["weakest_bars"]:
                            self.learner_progress.record_saved_trouble(plan,
                                fingerprint=state.binding.fingerprint,
                                phrase_start=state.course.stage.variant.phrase.start, assessed_notes=result.notes,
                                start=unit["start_beat"], end=unit["end_beat"], errors=unit["errors"])
                plan.apply_teaching_progress(decision.progress_after,
                    definition=decision.definition_after, expected=expected)
                hook = getattr(plan.lesson_generator, "with_feedback", None)
                if callable(hook) and decision.feedback_after != state.source_feedback:
                    plan.lesson_generator = hook(dict(decision.feedback_after), decision.definition_after)
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
                continuation.restore_state(continuation_before)
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
        """Reset the exact piece and its source feedback with one savepoint."""
        with self.capture.atomic():
            self.capture.interrupt("lesson_reset",played)
            self.capture.flush_intervals(now)
            self.repository.reset_piece(fingerprint)
            self.source_feedback.reset(fingerprint)
            self.repository.save(replacement,fingerprint)
            self.capture.event("lesson_reset",{
                "fingerprint":fingerprint,"preserves_history":True})

    def finish_preview(self) -> None:
        """Preview cannot award assessment, evidence credit or mastery."""
        self.capture.seal((),state="completed",reason="preview")
        with self.capture.atomic():
            self.capture.persist()
        self.capture.finish()

    def checkpoint(self, played, *, boundary: float) -> None:
        self.capture.checkpoint(played,boundary=boundary)

    def seal_rolling_recovery(self, pending, *, played, result,
                              end_beat: float, plan, binding, now,
                              policy) -> None:
        """One evidence writer for interrupted rolling-window recovery."""
        self.capture.seal(
            played,state="interrupted",reason="rolling_recovery",
            result=result,extra={"assessed_end_beat":end_beat})
        self.settle(pending,plan=plan,binding=binding,now=now,policy=policy)

    def seal_guided_preparation(self, pending, *, guidance: dict,
                                plan, binding, now, policy) -> None:
        """Atomically finish a completed guided attempt and its decision.

        The capture seal precedes the single idempotent settlement, matching
        the source-constrained evidence schema. On storage failure the engine
        preserves the same active exposure and may retry the same decision.
        """
        self.capture.seal(
            self.capture.guided.presses,state="completed",
            reason="guided_preparation",extra={"guidance":guidance})
        self.settle(pending,plan=plan,binding=binding,now=now,policy=policy)

    def seal_completed_take(self, pending, *, played, route: str,
                            mode: str, at_target: bool, assessed_end_beat: float,
                            result, plan, binding, now, policy,
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
                    policy=policy,performance_summary=(
                        performance_summary if route == "perform" else None))
        return True

    def cancel(self, pending=None, *, reason, now):
        if pending is not None and pending is not self.pending:
            return
        self.pending = None
        self._completion = None
        self._full_completion = None
        self._rolling = None
        self.cancellation_generation += 1

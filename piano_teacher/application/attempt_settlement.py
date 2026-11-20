"""Decision lifetime and atomic evidence/progress installation.

This owner has no engine, transport or renderer reference. Preparation chooses
once; checkpoint and settlement apply only the recorded immutable effects.
"""
from __future__ import annotations
from dataclasses import dataclass, replace, asdict
from ..teaching_decisions import validate_teaching_decision
from .mistake_responses import mistake_policy_facts


@dataclass(slots=True)
class PendingTeachingDecision:
    event: object
    state: object
    decision: object
    assessment: object
    checkpoint_progress: object = None
    phase: str = "decided"
    receipt: object = None


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


class AttemptSettlement:
    def __init__(self, repository, capture, source_feedback, learner_progress):
        self.repository = repository
        self.capture = capture
        self.source_feedback = source_feedback
        self.learner_progress = learner_progress
        self.pending = None
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
        pending = PendingTeachingDecision(event, state, decision, event.assessment)
        self.pending = pending
        return pending

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

    def seal_missing_full_passage(self, pending, *, played) -> None:
        """Preserve an already-selected verdict if capture was not sealed."""
        if self.capture.attempt_id is None or self.capture.sealed is not None:
            return
        self.capture.seal(
            played,state="completed",reason="full_passage",
            result=pending.assessment,
            eligible=pending.decision.mastery_eligible,
            verdict=pending.decision.verdict)

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
        self.cancellation_generation += 1

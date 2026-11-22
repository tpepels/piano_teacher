"""Prepare and apply the single accepted teaching decision.

Uses exact source, persisted learner progress, evidence and the current policy
instance. This application service does not own an independent curriculum
planner, score renderer, transport or engine reference.
"""
from __future__ import annotations
from dataclasses import dataclass
from ..teaching_decisions import validate_teaching_decision
from ..teaching_decisions import (
    TeachingBinding, TeachingState, TeachingRouteFacts, TeachingEvent)
from ..teaching_manual import ManualFacts
from ..diagnosis_policies import LearnerSnapshot
from ..completion_route import completion_route
from .mistake_responses import resolve_mistake_policy
from .learning_capture import identifier


@dataclass(frozen=True, slots=True)
class CommandEffect:
    """One validated teaching decision for the selected source state."""
    event: object
    state: object
    decision: object


class TeachingDecisions:
    def __init__(self, *, source_identity, lesson_cursor, attempt,
                 attempt_settlement, measurement, playback_session,
                 visual_transport, guided_session, recovery_streak,
                 policy_registry, library, fukuda_mistakes, learner_progress,
                 session_commands, learning_evidence, clock):
        self.source_identity = source_identity
        self.lesson_cursor = lesson_cursor
        self.attempt = attempt
        self.attempt_settlement = attempt_settlement
        self.measurement = measurement
        self.playback_session = playback_session
        self.visual_transport = visual_transport
        self.guided_session = guided_session
        self.recovery_streak = recovery_streak
        self.policy_registry = policy_registry
        self.library = library
        self.fukuda_mistakes = fukuda_mistakes
        self.learner_progress = learner_progress
        self.session_commands = session_commands
        self._last_applied_command = None
        self.learning_evidence = learning_evidence
        self.clock = clock

    def retry_context(self, result, *, end_beat=None):
        return self.learning_evidence.adaptive_context(
            result, plan=self.source_identity.plan, fingerprint=self.source_identity.fingerprint,
            from_beat=self.visual_transport.play_from_beat,
            end_beat=end_beat)

    def valid_trouble_spots(self, *, stage_key: str | None = None) -> list[dict]:
        return self.learner_progress.valid_trouble_spots(
            self.source_identity.plan, fingerprint=self.source_identity.fingerprint, stage_key=stage_key)

    def binding(self):
        owner = self.attempt_settlement
        return TeachingBinding(self.measurement.run_id, self.measurement.session_id,
            self.source_identity.fingerprint, self.source_identity.plan.identity, owner.course_revision,
            owner.authority_revision, self.playback_session.transport_id, owner.cancellation_generation)

    def prepare(self, kind, result=None, *, rolling=None, manual=None, action=None,
                          from_beat=None, end_beat=None, store=True, values=None, completed=False, assisted_count=0):
        p = self.source_identity.plan
        values = values or {}
        event = TeachingEvent(1, (identifier() if kind in ("manual","interrupted","source_feedback_changed") else self.measurement.attempt_id or identifier())+":"+kind+(":"+str(end_beat) if kind == "rolling_result" else ""), kind,
            self.measurement.attempt_id, result, rolling, manual, action, from_beat, end_beat,
            assisted_count=assisted_count, completed=completed, reason=values.get("reason"),
            bar=values.get("bar"), first_bar=values.get("first_bar"), last_bar=values.get("last_bar"),
            scope=values.get("scope"), requested_stage=values.get("stage_key"), requested_mode=values.get("mode"))
        scope = completion_route(self.playback_session.mode, self.attempt.review_end_beat,
            self.visual_transport.play_from_beat,
            full_from_beat=p.active_phrase.first_attack_beat)
        if self.attempt.automatic_remedial_review and scope == "section_review":
            scope = "partial_recovery"
        policy = resolve_mistake_policy(self.library.settings["mistake_response_strategy"])
        history = (self.policy_registry.learning.store.recent(self.source_identity.fingerprint, p.identity)
                   if self.source_identity.fingerprint else LearnerSnapshot(p.identity, ()))
        state = TeachingState(1, self.binding(), p.course_state(), policy,
            tuple(sorted(self.fukuda_mistakes.evidence(self.source_identity.fingerprint).items())) if self.source_identity.fingerprint else (),
            history, self.retry_context(result, end_beat=end_beat) if result is not None and (policy.whole_handler is not None or policy.rolling_handler is not None) else None,
            TeachingRouteFacts(mode=self.playback_session.mode, automatic=self.playback_session.auto, warmup=self.source_identity.warmup,
                preview_only=self.playback_session.preview_only, assistance_used=self.measurement.assistance_used,
                scope=scope, performed_bpm=self.attempt_settlement.pending_assessed_bpm or p.bpm,
                from_beat=self.visual_transport.play_from_beat,
                end_beat=end_beat if end_beat is not None else p.active_phrase.sounding_end-p.active_phrase.start,
                course_guided=self.lesson_cursor.course_guided, guided_return=self.guided_session.return_context,
                guided_range=self.guided_session.beat_range, review_end_beat=self.attempt.review_end_beat,
                remediation_active=self.attempt.remediation_active is not None,
                trouble_key=self.recovery_streak.key, trouble_count=self.recovery_streak.count,
                parent_decision_id=self.measurement.parent_decision),
            self.policy_registry.learning.diagnosis, self.policy_registry.learning.learner,
            getattr(p.lesson_generator, "catalog", None),
            ManualFacts(credits=self.learner_progress.teaching_credits(self.source_identity.fingerprint),
                trouble=tuple((unit["stage_key"],unit["start_beat"],unit["end_beat"],tuple(unit["source_indices"]))
                    for unit in self.valid_trouble_spots()),
                review=tuple((u["first_bar"],u["last_bar"],u["start_beat"],u["end_beat"],u["errors"])
                    for u in (self.attempt.performance_summary or {}).get("sections",())),
                review_current=self.attempt.review_stage_identity == p.identity,
                paused=self.visual_transport.paused,
                guidance_completed=bool(self.guided_session.controller is not None and self.guided_session.controller.snapshot(now=self.clock())["completed"]),
                open_from_beat=self.lesson_cursor.opening_beat,pending_rewind=self.visual_transport.pending_rewind))
        if not store:
            decision = p.lesson_generator.decide_teaching(event, state)
            validate_teaching_decision(decision, event=event, state=state)
            return CommandEffect(event, state, decision)
        return self.attempt_settlement.prepare(event=event, state=state, generator=p.lesson_generator)

    def manual_effect(self, action, *, from_beat=None, values=None):
        return self.session_commands.active or self.prepare("manual", action=action,
            from_beat=from_beat, values=values, store=False)

    def apply_progress(self, effect) -> bool:
        """Apply exactly one validated manual decision to the lesson owner.

        Keep a source-bound idempotence identity here, not in the command
        dispatch/context adapter. The exposure awaiting timed playback is
        published only after the learner's progress was accepted.
        """
        if self._last_applied_command is effect:
            return False
        plan = self.source_identity.plan
        plan.apply_teaching_progress(
            effect.decision.progress_after,
            definition=effect.decision.definition_after,
            expected=effect.decision.before_progress)
        self._last_applied_command = effect
        self.session_commands.prepare_exposure(effect.decision.next_exposure)
        return True

    def install_command(self, effect):
        current = self.source_identity.plan.teaching_progress()
        if current == effect.decision.before_progress:
            if self.apply_progress(effect):
                self.attempt_settlement.command_applied()
        elif current != effect.decision.progress_after:
            raise ValueError("Manual teaching progress changed before application")
        return effect.decision.next_exposure


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
from ..completion_route import completion_route
from .learning_capture import identifier


@dataclass(frozen=True, slots=True)
class CommandEffect:
    """One validated teaching decision for the selected source state."""
    event: object
    state: object
    decision: object


class TeachingDecisions:
    def __init__(self, *, source_identity, lesson_cursor, take, measurement,
                          transport, guided_session, learner_progress, clock):
        self.source_identity = source_identity
        self.lesson_cursor = lesson_cursor
        self.take = take
        self.measurement = measurement
        self.transport = transport
        self.guided_session = guided_session
        self.learner_progress = learner_progress
        self._last_applied_command = None
        self.clock = clock

    def binding(self):
        owner = self.take
        return TeachingBinding(self.measurement.run_id, self.measurement.session_id,
            self.source_identity.fingerprint, self.source_identity.plan.identity, owner.course_revision,
            owner.authority_revision, self.transport.transport_id, owner.cancellation_generation)

    def prepare(self, kind, result=None, *, manual=None, action=None,
                          from_beat=None, end_beat=None, store=True, values=None, completed=False, assisted_count=0):
        p = self.source_identity.plan
        values = values or {}
        event = TeachingEvent(1, (identifier() if kind in ("manual","interrupted") else self.measurement.attempt_id or identifier())+":"+kind, kind,
            self.measurement.attempt_id, result, manual, action, from_beat, end_beat,
            assisted_count=assisted_count, completed=completed, reason=values.get("reason"),
            bar=values.get("bar"), first_bar=values.get("first_bar"), last_bar=values.get("last_bar"),
            scope=values.get("scope"), requested_stage=values.get("stage_key"), requested_mode=values.get("mode"))
        scope = completion_route(self.transport.mode, self.take.review_end_beat,
            self.transport.play_from_beat,
            full_from_beat=p.active_phrase.first_attack_beat)
        if self.take.automatic_remedial_review and scope == "section_review":
            scope = "partial_recovery"
        state = TeachingState(1, self.binding(), p.course_state(),
            TeachingRouteFacts(mode=self.transport.mode, automatic=self.transport.auto,
                preview_only=self.transport.preview_only, assistance_used=self.measurement.assistance_used,
                scope=scope, performed_bpm=self.take.pending_assessed_bpm or p.bpm,
                from_beat=self.transport.play_from_beat,
                end_beat=end_beat if end_beat is not None else p.active_phrase.sounding_end-p.active_phrase.start,
                course_guided=self.lesson_cursor.course_guided, guided_return=self.guided_session.return_context,
                guided_range=self.guided_session.beat_range, review_end_beat=self.take.review_end_beat,
                remediation_active=self.take.remediation_active is not None,
                parent_decision_id=self.measurement.parent_decision),
            ManualFacts(credits=self.learner_progress.teaching_credits(self.source_identity.fingerprint),
                paused=self.transport.paused,
                guidance_completed=bool(self.guided_session.controller is not None and self.guided_session.controller.snapshot(now=self.clock())["completed"]),
                open_from_beat=self.lesson_cursor.opening_beat,pending_rewind=self.transport.pending_rewind))
        if not store:
            decision = p.lesson_generator.decide_teaching(event, state)
            validate_teaching_decision(decision, event=event, state=state)
            return CommandEffect(event, state, decision)
        return self.take.prepare_settlement(event=event, state=state, generator=p.lesson_generator)

    def manual_effect(self, action, *, from_beat=None, values=None, effect=None):
        return effect or self.prepare(
            "manual", action=action, from_beat=from_beat, values=values, store=False)

    def source_installed(self) -> None:
        """Drop source-specific manual decisions after source installation."""
        self._last_applied_command = None

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
        return True

    def install_command(self, effect):
        current = self.source_identity.plan.teaching_progress()
        if current == effect.decision.before_progress:
            if self.apply_progress(effect):
                self.take.command_applied()
        elif current != effect.decision.progress_after:
            raise ValueError("Manual teaching progress changed before application")
        return effect.decision.next_exposure


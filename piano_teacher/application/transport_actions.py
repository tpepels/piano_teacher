"""Transport actions and exact graphical playback authorization.

Consumes the current source, one PlaybackCoordinator receipt and one timed
transport. No application command-router backreference or nested control call.
"""
from __future__ import annotations
from .playback_facts import PreparationRequest
from .playback_transitions import PlaybackTransition


class TransportActions:
    def __init__(self, *,
                 attempt, attempt_settlement, clock, exposure_workflows,
                 feedback_seconds, guided_session, lesson_cursor, lesson_execution,
                 lifecycle, listen, notices, completion_continuations,
                 playback, playback_session, read_models, recovery_workflows,
                 score_artifact_registry, score_read, source_identity,
                 teaching_decisions, timed_playback, transport_timing, visual_transport):
        self.attempt = attempt
        self.attempt_settlement = attempt_settlement
        self.clock = clock
        self.exposure_workflows = exposure_workflows
        self.feedback_seconds = feedback_seconds
        self.guided_session = guided_session
        self.lesson_cursor = lesson_cursor
        self.lesson_execution = lesson_execution
        self.lifecycle = lifecycle
        self.listen = listen
        self.notices = notices
        self.completion_continuations = completion_continuations
        self.playback = playback
        self.playback_session = playback_session
        self.read_models = read_models
        self.recovery_workflows = recovery_workflows
        self.score_artifact_registry = score_artifact_registry
        self.score_read = score_read
        self.source_identity = source_identity
        self.teaching_decisions = teaching_decisions
        self.timed_playback = timed_playback
        self.transport_timing = transport_timing
        self.visual_transport = visual_transport

    def enable_presentation(self) -> None:
        self.playback.enable_presentation(self.transport_timing.playback_facts())

    def reserve_physical(self, **values) -> dict:
        return self.playback.reserve(self.transport_timing.playback_facts(), **values)

    def present_physical(self, **values) -> dict:
        return self.playback.present(
            self.transport_timing.playback_facts(),
            commit=self.commit_playback_intent,
            capture=self.transport_timing.playback_facts,
            abort=self.abort_playback, **values)

    def withdraw_physical(self, **values) -> dict:
        return self.playback.withdraw(self.transport_timing.playback_facts(), **values)

    def fail_physical(self, **values) -> dict:
        self.playback.fail(notify_failure=self.on_playback_failure, **values)
        return {"accepted": True}

    def abort_playback(self, reason: str) -> None:
        self.lifecycle.stop(reason=reason)

    def on_playback_failure(self, reason: str) -> None:
        if self.playback_session.running:
            self.lifecycle.stop(reason=reason)
        self.notices.feedback = "The score stopped displaying correctly"
        self.notices.next_action = "Select this lesson again after checking the score."

    def commit_playback_intent(self, intent, receipt) -> None:
        """Apply source effects at the coordinator's single authorization gate."""
        with self.playback_session.authorization(intent,receipt) as authorized:
            if authorized.action in ("start","restart"):
                selected = self.teaching_decisions.install_command(authorized.transition.effect)
                authorized.validate_installed(selected,intent)
                self.timed_playback.start(mode=selected.mode,from_beat=selected.from_beat,
                    scheduled_deadline=authorized.deadline,count_in_plan=intent.count_in,
                    effect=authorized.transition.effect,reason=authorized.action)
            elif authorized.action == "resume":
                self.resume_current_session(
                    presentation_lead_seconds=max(0.0,authorized.deadline-self.clock()),
                    scheduled_deadline=authorized.deadline)
            elif authorized.action in ("auto","score_ready"):
                self.timed_playback.start(from_beat=intent.from_beat,mode=intent.mode,
                    loop_continuation=authorized.action == "auto",
                    decided=False,scheduled_deadline=authorized.deadline,
                    count_in_plan=intent.count_in,reason=authorized.action)
                self.visual_transport.bind_scheduled_start(
                    transport_id=self.playback_session.transport_id,
                    from_beat=self.visual_transport.play_from_beat,
                    run_at=self.visual_transport.run_at,
                    stage_key=self.source_identity.plan.identity,
                    revision=self.source_identity.revision)
            elif authorized.action == "listen":
                self.playback_session.start_listen(revision=self.source_identity.revision,
                    count_in=intent.count_in,deadline=authorized.deadline)
                self.notices.feedback = "Count in, then listen"

    def control_acknowledgement(self, action: str, kwargs: dict, *, reason=None) -> None:
        if action == "score_ready":
            # The compiled native score has now supplied real printed rest
            # and header clearance. Install it before the score-ready ACK
            # can select a future fixed-deadline automatic continuation.
            self.transport_timing.update_short_rest(kwargs)
            revision = int(kwargs.get("revision",-1))
            decision = self.playback_session.score_acknowledged(revision,
                current_revision=self.source_identity.revision,teaching_bound=self.guided_session.controller is not None)
            if decision == "listen":
                self.timed_playback.begin_listen_if_ready()
            elif decision == "learn":
                self.guided_session.controller.start(now=self.clock())
            elif decision == "practice":
                position = (self.visual_transport.pending_rewind
                    if self.visual_transport.pending_rewind is not None else self.lesson_cursor.opening_beat)
                mode = "perform" if self.playback_session.mode == "perform" else "practice"
                if self.playback.presentation_required:
                    self.transport_timing.request_playback(action="score_ready",mode=mode,from_beat=position)
                    return
                announce = self.visual_transport.short_rest is not None or self.lesson_execution.flow_active()
                timing = self.playback_session.headless_ready_timing(
                    reserved_ms=kwargs.get("presentation_deadline_ms"),
                    count_in_beats=self.transport_timing.next_count_in_beats(),bpm=self.source_identity.plan.bpm,
                    announce=announce,rest=(self.transport_timing.collect_rest_measurement(
                        from_beat=self.lesson_cursor.opening_beat) if announce and
                        kwargs.get("presentation_deadline_ms") is None else None),
                    presentation_bpm=self.transport_timing.presentation_bpm())
                self.timed_playback.start(from_beat=position,mode=mode,scheduled_deadline=timing.deadline,
                    presentation_lead_seconds=timing.lead_seconds,decided=True,
                    reason=reason or action)
                if announce:
                    self.visual_transport.bind_scheduled_start(
                        transport_id=self.playback_session.transport_id,
                        from_beat=self.visual_transport.play_from_beat,
                        run_at=self.visual_transport.run_at,
                        stage_key=self.source_identity.plan.identity,
                        revision=self.source_identity.revision)
        elif self.playback_session.mode == "listen" and self.listen.acknowledge_audio(kwargs.get("token")):
            self.timed_playback.begin_listen_if_ready()

    def control_transport(self, action: str, kwargs: dict, *, effect=None) -> None:
        if action == "practice":
            self.exposure_workflows.prepare_practice(effect=effect,reason=action)
            if kwargs.get("wait_for_player", False):
                # Listen returns to a ready score without an auto count-in.
                self.playback_session.wait_for_player()
                self.notices.feedback = "Ready to play"
                self.notices.next_action = "Play one piano key to begin, or press Play."
        elif action == "stop":
            self.lifecycle.stop(reason="stop")
            # A stopped session has no take a later rest could follow (M6).
            self.visual_transport.clear_take_end()
            self.notices.feedback = "Stopped"
            self.notices.next_action = "Start when you are ready."
        elif action in ("start", "restart"):
            self.transport_timing.update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self.transport_timing.update_short_rest(kwargs)
            if self.playback.presentation_required:
                if self.attempt.settlement_failed or self.attempt_settlement.pending_rolling is not None:
                    self.start_or_restart(action, effect=effect)
                    return
                effect = effect or self.teaching_decisions.manual_effect(action)
                transition = PlaybackTransition.from_effect(
                    effect,action=action,source_changed=(
                        self.score_artifact_registry.current.source_bpm_changed(self.source_identity.plan.piece.bpm)
                        if self.playback_session.mode not in ("listen", "learn") else False))
                if transition.route in ("listen", "prepare_practice",
                                        "reload_score", "learn"):
                    # These routes change assets or enter untimed teaching.
                    # The resulting timed source, if any, is requested only
                    # after its exact selected score revision is prepared.
                    self.start_or_restart(action, effect=effect)
                else:
                    selected = transition.exposure
                    self.transport_timing.request_playback( action=action,
                        mode=selected.mode, from_beat=selected.from_beat,
                        transition=transition)
            else:
                self.start_or_restart(
                    action, effect=effect,
                    presentation_lead_seconds=self.transport_timing.presentation_lead(kwargs))
        elif action == "pause":
            self.timed_playback.pause(
                pending_admission=self.playback_session.suspend_admission(self.playback))
        elif action == "resume":
            self.transport_timing.update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self.transport_timing.update_short_rest(kwargs)
            if self.playback.presentation_required:
                suspended = self.playback_session.take_suspended_admission()
                if suspended is not None:
                    self.transport_timing.request_playback(action=suspended.action,
                        mode=suspended.mode,from_beat=suspended.from_beat,
                        transition=suspended.transition)
                    return
                if not self.playback_session.running:
                    # Resume inside a rest resumes the pending teaching
                    # decision; it is not a new timed take. Its next take
                    # will independently enter the admission transaction.
                    self.resume_current_session()
                    return
                from_beat = self.visual_transport.play_from_beat
                if self.playback_session.running:
                    from_beat += max(0.0, self.transport_timing.elapsed_beat(
                        self.visual_transport.paused_at
                        - self.visual_transport.run_at))
                self.transport_timing.request_playback( action="resume",
                    mode=self.playback_session.mode, from_beat=from_beat)
            else:
                self.resume_current_session(presentation_lead_seconds=self.transport_timing.presentation_lead(kwargs),
                    reuse_announced_score=kwargs.get("reuse_announced_score",False) is True)

    def start_or_restart(self, action: str, *,
                          presentation_lead_seconds: float = 0.0,
                          scheduled_deadline: float | None = None, effect=None):
        """Start a take or schedule a seamless retry under the control lock."""
        if self.attempt.settlement_failed:
            revision = self.source_identity.revision
            self.notices.feedback = self.completion_continuations.commit_pending() or "Assessment saved"
            if self.source_identity.revision != revision:
                self.playback_session.await_score(self.source_identity.revision)
            self.notices.next_action = "Press Play when the score is ready."
            return
        if self.attempt_settlement.pending_rolling is not None:
            decision, phrase, grid, score_beat, _old_now = self.attempt_settlement.pending_rolling
            self.recovery_workflows.apply_rolling_recovery(decision, phrase, grid, score_beat, self.clock())
            self.visual_transport.clear_pause_for_restart()
            return
        p = self.source_identity.plan
        if p is None:
            raise ValueError("Open a piece first")
        effect = self.teaching_decisions.manual_effect(action, effect=effect)
        selected = self.teaching_decisions.install_command(effect)
        route = PlaybackTransition.from_effect(
            effect,action="start",source_changed=(
            self.score_artifact_registry.current.source_bpm_changed(p.piece.bpm)
            if self.playback_session.mode not in ("listen","learn") else False)).route
        if route == "listen":
            self.exposure_workflows.prepare_listen(effect=effect,reason=action)
            return
        if route == "prepare_practice":
            self.exposure_workflows.prepare_practice(exposure=selected,reason=action)
            return
        if route == "learn":
            self.lesson_execution.begin_learn(exposure=selected,reason=action)
            return
        if route == "reload_score":
            self.lifecycle.stop(reason=action)
            self.source_identity.advance_revision()
            self.playback_session.await_score(self.source_identity.revision)
            self.notices.feedback = "Preparing sheet music"
            return
        if route == "rewind":
            sampled = self.clock()
            visual_now = self.visual_transport.paused_at if self.visual_transport.paused else sampled
            position,_,_ = self.transport_timing.visual_motion(visual_now)
            self.playback_session.prepare_retry(PreparationRequest(
                self.score_read.source_model(),selected.from_beat,sampled,position,self.feedback_seconds,
                self.transport_timing.presentation_bpm(),self.visual_transport.continuous_horizon_beats,
                reading_lead_included=presentation_lead_seconds > 0,
                short_deadline=scheduled_deadline),
                presentation_lead_seconds=presentation_lead_seconds,source_bpm=p.bpm)
            self.notices.feedback = "Get ready to retry"
            return
        self.timed_playback.start(mode=selected.mode,from_beat=selected.from_beat,decided=True,
                   scheduled_deadline=scheduled_deadline,
                   presentation_lead_seconds=presentation_lead_seconds,reason=action)
        return

    def resume_current_session(self, *, presentation_lead_seconds=0.0,
                                reuse_announced_score=False,
                                scheduled_deadline=None):
        completed = self.timed_playback.resume(
            presentation_lead_seconds=presentation_lead_seconds,
            reuse_announced_score=reuse_announced_score,
            scheduled_deadline=scheduled_deadline)
        if completed.deferred_score_revision is not None:
            # Infrastructure acknowledgement stays within this transaction.
            # Re-entering control() from Resume would recursively start a
            # second command scope and repeat the application router.
            self.control_acknowledgement(
                "score_ready", {"revision": completed.deferred_score_revision},
                reason="score_ready")
            self.read_models.prepare_score_presentation()
        self.timed_playback.begin_listen_if_ready()


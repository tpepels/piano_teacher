"""One locked public command router and exact graphical playback authorization gate.

This layer applies explicit user/native actions through source-bound
application services. Teaching, grading, clock and ink owners remain separate.
No alternate command queue or independent admission state is introduced.
"""
from __future__ import annotations
from .control_dispatch import ControlDispatcher
from .stage_change import prepare_stage_change
from .playback_facts import PreparationRequest


class PracticeControls:
    def __init__(self, *, source_identity, lesson_cursor, notices, lock,
                 session_commands, playback_session, playback, attempt,
                 attempt_settlement, timed_playback, transport_timing,
                 score_read, score_artifact_registry, guided_session,
                 flow_session, listen, midi, midi_key_shortcuts,
                 teaching_decisions, exposure_workflows, lesson_execution,
                 outcome_effects, recovery_workflows,
                 history_management, device_workflows, settings_workflows,
                 measurement, visual_transport, progress, lifecycle,
                 read_models, clock, feedback_seconds):
        self.source_identity, self.lesson_cursor, self.notices = source_identity, lesson_cursor, notices
        self.lock, self.session_commands = lock, session_commands
        self.playback_session, self.playback, self.attempt = playback_session, playback, attempt
        self.attempt_settlement, self.timed_playback = attempt_settlement, timed_playback
        self.transport_timing, self.score_read = transport_timing, score_read
        self.score_artifact_registry, self.guided_session = score_artifact_registry, guided_session
        self.flow_session, self.listen, self.midi = flow_session, listen, midi
        self.midi_key_shortcuts, self.teaching_decisions = midi_key_shortcuts, teaching_decisions
        self.exposure_workflows, self.lesson_execution = exposure_workflows, lesson_execution
        self.outcome_effects, self.recovery_workflows = outcome_effects, recovery_workflows
        self.history_management = history_management
        self.device_workflows, self.settings_workflows = device_workflows, settings_workflows
        self.measurement, self.visual_transport, self.progress = measurement, visual_transport, progress
        self.lifecycle, self.read_models, self.clock = lifecycle, read_models, clock
        self.feedback_seconds = feedback_seconds

    def _stop(self, *, reason=None, preserve_episode=False, persist_evidence=True) -> None:
        self.lifecycle.stop(reason=reason or self.session_commands.action_reason,
                            preserve_episode=preserve_episode, persist_evidence=persist_evidence)

    def _save(self) -> None:
        self.progress.save(self.source_identity.plan, self.source_identity.fingerprint)

    def calibration_action(self, action: str) -> None:
        changes = self.device_workflows.calibrate(
            action, stop_reason=self.session_commands.action_reason)
        if changes is not None:
            self.settings_workflows.update(
                changes, pause_current=self.timed_playback.pause)

    def abort_playback(self, reason: str) -> None:
        self._stop(reason=reason)

    def on_playback_failure(self, reason: str) -> None:
        if self.playback_session.running:
            self._stop(reason=reason)
        self.notices.feedback = "The score stopped displaying correctly"
        self.notices.next_action = "Select this lesson again after checking the score."

    def commit_playback_intent(self, intent, receipt) -> None:
        """Apply source effects at the coordinator's single authorization gate."""
        with self.playback_session.authorization(intent,receipt) as authorized:
            if authorized.action in ("start","restart"):
                selected = self.teaching_decisions.install_command(authorized.transition.effect)
                authorized.validate_installed(selected,intent)
                with self.session_commands.executing(authorized.transition.effect):
                    self.timed_playback.start(mode=selected.mode,from_beat=selected.from_beat,
                        scheduled_deadline=authorized.deadline,count_in_plan=intent.count_in)
            elif authorized.action == "resume":
                self.resume_current_session(
                    presentation_lead_seconds=max(0.0,authorized.deadline-self.clock()),
                    reuse_pending_score=receipt.reused_count_in,
                    scheduled_deadline=authorized.deadline)
            elif authorized.action in ("auto","score_ready"):
                with self.session_commands.executing(None):
                    self.timed_playback.start(from_beat=intent.from_beat,mode=intent.mode,
                        loop_continuation=authorized.action == "auto",
                        decided=False,scheduled_deadline=authorized.deadline,
                        count_in_plan=intent.count_in)
                self.visual_transport.scheduled_start = (
                    self.playback_session.transport_id,self.visual_transport.play_from_beat,
                    self.visual_transport.run_at,self.source_identity.plan.identity,self.source_identity.revision,None)
            elif authorized.action == "listen":
                self.playback_session.start_listen(revision=self.source_identity.revision,
                    count_in=intent.count_in,deadline=authorized.deadline)
                self.notices.feedback = "Count in, then listen"

    def control(self, action: str, **kwargs) -> None:
        with self.lock:
            previous_reason = self.session_commands.action_reason
            self.session_commands.action_reason = action
            before = {"fingerprint": self.source_identity.fingerprint,
                      "stage_key": self.source_identity.plan.identity if self.source_identity.plan else None,
                      "bpm": self.source_identity.plan.bpm if self.source_identity.plan else None, "mode": self.playback_session.mode}
            effect = self.session_commands.active
            route = ControlDispatcher.route(action)
            if self.source_identity.plan is not None and route in ("listening", "learning", "transport", "stage") and not (action in ("start","restart") and (self.attempt.settlement_failed or self.attempt_settlement.pending_rolling is not None)):
                change = (prepare_stage_change(self.source_identity.plan, action, kwargs, warmup=self.source_identity.warmup)
                          if route == "stage" else None)
                effect = self.teaching_decisions.prepare("manual", manual=change,
                    action=action, from_beat=kwargs.get("from_beat",kwargs.get("start_beat")), store=False, values=kwargs)
            try:
                with self.session_commands.executing(effect):
                    result = self.dispatch_control(action, **kwargs)
                    self.read_models.prepare_score_presentation()
                    if action not in ("score_ready", "demo_ready", "reset_path"):
                        self.measurement.event("manual_action", {"action": action,
                            "fingerprint": before["fingerprint"] or None,
                            "parameters": kwargs, "before": before,
                            "after": {"fingerprint": self.source_identity.fingerprint,
                                      "stage_key": self.source_identity.plan.identity if self.source_identity.plan else None,
                                      "bpm": self.source_identity.plan.bpm if self.source_identity.plan else None, "mode": self.playback_session.mode}})
                    return result
            finally:
                self.session_commands.action_reason = previous_reason

    def dispatch_control(self, action: str, **kwargs) -> None:
        """Single locked command entry; dispatch owns no engine state."""
        with self.lock:
            self.exposure_workflows.apply_listen_failure()
            route = ControlDispatcher.route(action)
            if route == "calibration":
                return self.calibration_action(action)
            if route == "device_range":
                if action == "midi_range_cancel":
                    self.midi_key_shortcuts.cancel_capture()
                else:
                    if not self.midi.connected:
                        raise ValueError("Connect a MIDI piano before setting its key range")
                    if self.playback_session.running and not self.visual_transport.paused:
                        self.timed_playback.pause()
                    self.midi_key_shortcuts.begin_capture(self.midi.device)
                return
            if route == "reset":
                return self.history_management.reset_current_path(
                    fingerprint=kwargs.get("fingerprint"),
                    confirm=kwargs.get("confirm") is True)
            if route == "acknowledgement":
                return self.control_acknowledgement(action, kwargs)
            if route == "listening":
                return self.control_listening(action, kwargs)
            if route == "learning":
                return self.control_learning(action, kwargs)
            if route == "transport":
                return self.control_transport(action, kwargs)
            return self.change_stage(action, kwargs)

    def control_acknowledgement(self, action: str, kwargs: dict) -> None:
        if action == "score_ready":
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
                    presentation_lead_seconds=timing.lead_seconds,decided=True)
                if announce:
                    self.visual_transport.scheduled_start = (
                        self.playback_session.transport_id,self.visual_transport.play_from_beat,
                        self.visual_transport.run_at,self.source_identity.plan.identity,self.source_identity.revision,None)
        elif self.playback_session.mode == "listen" and self.listen.acknowledge_audio(kwargs.get("token")):
            self.timed_playback.begin_listen_if_ready()

    def control_listening(self, action: str, kwargs: dict) -> None:
        if action == "listen":
            if (self.lesson_execution.flow_active() and self.flow_session.state is not None
                    and self.flow_session.state.stage_key == self.source_identity.plan.identity
                    and self.playback_session.mode != "listen"):
                # Listen again: the state machine plays it, then Free.
                self.lesson_execution.flow_execute(self.flow_session.listen_again())
            else:
                self.exposure_workflows.prepare_listen()
        elif action == "perform":
            self.exposure_workflows.prepare_perform(scope=str(kwargs.get("scope", "current")))
        elif action == "practice_weak":
            self.lesson_execution.practice_weak()
        elif action == "review_retry":
            self.lesson_execution.review_retry(kwargs.get("first_bar"), kwargs.get("last_bar"))
        elif action == "seek":
            self.lesson_execution.seek(kwargs.get("bar"))

    def control_learning(self, action: str, kwargs: dict) -> None:
        if action == "learn_next":
            if (self.playback_session.mode != "learn" or self.guided_session.controller is None
                    or not self.guided_session.controller.snapshot(now=self.clock())["completed"]):
                raise ValueError("Find the current notes before continuing to the next idea")
            self.lesson_execution.save_guided_preparation()
            if self.guided_session.return_context is not None:
                self.exposure_workflows.prepare_practice()
            else:
                self.lesson_execution.begin_course_stage()
        elif action == "skip_stage":
            if self.source_identity.warmup:
                raise ValueError("Warm-up stages unlock after three clean runs, not skips")
            self.lesson_execution.skip_stage(kwargs.get("reason"))
        elif action == "place_original":
            if self.source_identity.warmup:
                raise ValueError("Warm-up stages unlock after three clean runs")
            self.lesson_execution.place_original()
        elif action == "revisit_trouble":
            self.lesson_execution.revisit_trouble(kwargs.get("stage_key"), kwargs.get("start_beat"))
        elif action in ("learn", "learn_retry"):
            if action == "learn":
                self.lesson_cursor.set_course_guided(True)
                if "from_beat" not in kwargs:
                    self.lesson_execution.begin_course_stage(explicit_learn=True)
                    return
            previous_start = (self.guided_session.beat_range[0]
                              if self.guided_session.beat_range else 0.0)
            self.lesson_execution.begin_learn(
                from_beat=float(kwargs.get(
                    "from_beat",
                    previous_start if action == "learn_retry" else 0.0)),
                recovery=self.guided_session.return_context is not None and action == "learn_retry")
        elif action == "open_at":
            self.open_selected_measure(kwargs)
        elif action == "hints":
            self.guided_session.set_hints(
                bool(kwargs.get("enabled", False)), now=self.clock())
            if kwargs.get("enabled", False) and self.measurement.attempt_id is not None:
                self.measurement.use_assistance()

    def control_transport(self, action: str, kwargs: dict) -> None:
        if action == "practice":
            self.exposure_workflows.prepare_practice()
            if kwargs.get("wait_for_player", False):
                # Listen returns to a ready score without an auto count-in.
                self.playback_session.wait_for_player()
                self.notices.feedback = "Ready to play"
                self.notices.next_action = "Play one piano key to begin, or press Play."
        elif action == "stop":
            self._stop(reason="stop")
            # A stopped session has no take a later rest could follow (M6).
            self.visual_transport.rest_take_end = None
            self.notices.feedback = "Stopped"
            self.notices.next_action = "Start when you are ready."
        elif action in ("start", "restart"):
            self.transport_timing.update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self.transport_timing.update_short_rest(kwargs)
            if self.playback.presentation_required:
                if self.attempt.settlement_failed or self.attempt_settlement.pending_rolling is not None:
                    self.start_or_restart(action)
                    return
                effect = self.session_commands.active or self.teaching_decisions.manual_effect(action)
                transition = self.session_commands.transition(
                    effect,action=action,source_changed=(
                        self.score_artifact_registry.current.source_bpm_changed(self.source_identity.plan.piece.bpm)
                        if self.playback_session.mode not in ("listen", "learn") else False))
                if transition.route in ("listen", "prepare_practice",
                                        "reload_score", "learn"):
                    # These routes change assets or enter untimed teaching.
                    # The resulting timed source, if any, is requested only
                    # after its exact selected score revision is prepared.
                    self.start_or_restart(action)
                else:
                    selected = transition.exposure
                    self.transport_timing.request_playback( action=action,
                        mode=selected.mode, from_beat=selected.from_beat,
                        transition=transition)
            else:
                self.start_or_restart(
                    action, presentation_lead_seconds=self.transport_timing.presentation_lead(kwargs))
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
                    reuse_pending_score=kwargs.get("reuse_pending_score",False) is True,
                    reuse_announced_score=kwargs.get("reuse_announced_score",False) is True)

    def open_selected_measure(self, kwargs: dict):
        effect = self.teaching_decisions.manual_effect("open_at",values=kwargs)
        self._stop()
        selected = self.teaching_decisions.install_command(effect)
        self.lesson_execution.reset_trouble()
        self.lesson_cursor.set_course_guided(selected.mode == "learn")
        self.lesson_cursor.select_opening(selected.from_beat)
        if selected.mode == "learn":
            self.lesson_execution.begin_learn(from_beat=selected.from_beat,exposure=selected)
        else:
            self.exposure_workflows.prepare_practice(exposure=selected)
            self.playback_session.wait_for_player()
            self.notices.feedback = f"Ready to practise from measure {kwargs.get('bar')}"
            self.notices.next_action = "Press Start to play from the selected measure."

    def start_or_restart(self, action: str, *,
                          presentation_lead_seconds: float = 0.0,
                          scheduled_deadline: float | None = None):
        """Start a take or schedule a seamless retry under the control lock."""
        if self.attempt.settlement_failed:
            revision = self.source_identity.revision
            self.notices.feedback = self.outcome_effects.commit_pending() or "Assessment saved"
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
        effect = self.teaching_decisions.manual_effect(action)
        selected = self.teaching_decisions.install_command(effect)
        route = self.session_commands.start_route(effect,source_changed=(
            self.score_artifact_registry.current.source_bpm_changed(p.piece.bpm)
            if self.playback_session.mode not in ("listen","learn") else False))
        if route == "listen":
            self.exposure_workflows.prepare_listen()
            return
        if route == "prepare_practice":
            self.exposure_workflows.prepare_practice(exposure=selected)
            return
        if route == "learn":
            self.lesson_execution.begin_learn(exposure=selected)
            return
        if route == "reload_score":
            self._stop()
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
                   presentation_lead_seconds=presentation_lead_seconds)
        return

    def change_stage(self, action: str, kwargs: dict):
        """Change the active lesson or tempo while preserving scoring state."""
        p=self.source_identity.plan
        if not p:
            raise ValueError("Open a piece first")
        change = prepare_stage_change(
            p, action, kwargs, warmup=self.source_identity.warmup)
        was_guided = self.playback_session.mode == "learn"
        guided_start = (self.guided_session.beat_range[0]
                        if self.guided_session.beat_range is not None else 0.0)
        guided_return = self.guided_session.return_context
        guided_retry_range = self.attempt.retry_range
        self._stop()
        self.lesson_execution.reset_trouble()
        # Preserve the original ordering of the source opening reset.
        if action in ("select_step", "next", "previous"):
            self.lesson_cursor.select_opening(0.0)
        effect = self.session_commands.active or self.teaching_decisions.prepare("manual", manual=change, action=action, store=False)
        self.session_commands.apply_progress(effect, plan=p)
        self.attempt_settlement.command_applied()
        if action == "hand":
            self.lesson_cursor.select_opening(0.0)
        # Native notation is engraved in source coordinates: changing
        # only playback BPM must not invalidate the score/reload Godot.
        if not change.tempo_only:
            self.source_identity.advance_revision()
        self.notices.feedback="Ready"
        self.notices.next_action="Start when you are ready."
        if was_guided:
            selected = effect.decision.next_exposure
            if selected is not None and selected.mode == "learn":
                recovery = change.tempo_only and guided_return is not None and guided_return[0] == p.identity
                if recovery:
                    self.attempt.restore_retry(guided_retry_range)
                self.lesson_execution.begin_learn(from_beat=selected.from_beat,bump_revision=False,recovery=recovery,exposure=selected)
            elif selected is not None:
                self.lesson_execution.enter_selected_exposure(selected)
        self._save()

    def resume_current_session(self, *, presentation_lead_seconds=0.0,
                                reuse_pending_score=False,
                                reuse_announced_score=False,
                                scheduled_deadline=None):
        completed = self.timed_playback.resume(
            presentation_lead_seconds=presentation_lead_seconds,
            reuse_pending_score=reuse_pending_score,
            reuse_announced_score=reuse_announced_score,
            scheduled_deadline=scheduled_deadline)
        if completed.deferred_score_revision is not None:
            self.control("score_ready", revision=completed.deferred_score_revision)
        self.timed_playback.begin_listen_if_ready()


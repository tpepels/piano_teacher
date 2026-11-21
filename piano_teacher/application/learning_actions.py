"""User-requested lesson and course navigation.

Applies generator-approved source progress, guided returns and selected lesson
positions through current state/persistence owners.
"""
from __future__ import annotations
from .stage_change import prepare_stage_change


class LearningActions:
    def __init__(self, *,
                 attempt, attempt_settlement, clock, exposure_workflows,
                 flow_session, guided_session, lesson_cursor, lesson_execution,
                 lifecycle, measurement, notices, playback_session,
                 progress, session_commands, source_identity, teaching_decisions):
        self.attempt = attempt
        self.attempt_settlement = attempt_settlement
        self.clock = clock
        self.exposure_workflows = exposure_workflows
        self.flow_session = flow_session
        self.guided_session = guided_session
        self.lesson_cursor = lesson_cursor
        self.lesson_execution = lesson_execution
        self.lifecycle = lifecycle
        self.measurement = measurement
        self.notices = notices
        self.playback_session = playback_session
        self.progress = progress
        self.session_commands = session_commands
        self.source_identity = source_identity
        self.teaching_decisions = teaching_decisions

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

    def open_selected_measure(self, kwargs: dict):
        effect = self.teaching_decisions.manual_effect("open_at",values=kwargs)
        self.lifecycle.stop(reason=self.session_commands.action_reason)
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

    def change_stage(self, action: str, kwargs: dict):
        """Change the active lesson or tempo while preserving scoring state."""
        p=self.source_identity.plan
        if not p:
            raise ValueError("Open a piece first")
        queued = self.session_commands.active
        change = (queued.event.manual
                  if queued is not None and queued.event.action == action
                  and queued.event.manual is not None
                  else prepare_stage_change(
                      p, action, kwargs, warmup=self.source_identity.warmup))
        was_guided = self.playback_session.mode == "learn"
        guided_return = self.guided_session.return_context
        guided_retry_range = self.attempt.retry_range
        self.lifecycle.stop(reason=self.session_commands.action_reason)
        self.lesson_execution.reset_trouble()
        # Preserve the original ordering of the source opening reset.
        if action in ("select_step", "next", "previous"):
            self.lesson_cursor.select_opening(0.0)
        effect = (queued if queued is not None and queued.event.action == action
                  else self.teaching_decisions.prepare(
                      "manual", manual=change, action=action, store=False))
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
        self.progress.save(self.source_identity.plan, self.source_identity.fingerprint)


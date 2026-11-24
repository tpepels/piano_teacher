"""The lesson's course flow and the learner's navigation commands.

CourseFlow executes the selected course step (Listen, Free, Tempo),
guided preparation and selected exposures; only the Practice Flow
generator selects stages and tempo. LessonNavigation applies seek, open
at a measure and stage/tempo changes, and answers the lesson read ports.
"""
from __future__ import annotations
from ..remediation import RemedialAssignment
from . import practice_flow
from .exposure_preparation import prepare_guided
from .stage_change import prepare_stage_change


class CourseFlow:
    def __init__(self, *, lesson, notices, exposure_workflows, transport, take,
                 progress, measurement, clock):
        self.lesson = lesson
        self.notices = notices
        self.exposure_workflows = exposure_workflows
        self.transport = transport
        self.take = take
        self.progress = progress
        self.measurement = measurement
        self.clock = clock

    def _save(self) -> None:
        self.progress.save(self.lesson.plan, self.lesson.fingerprint)

    def save_guided_preparation(self):
        guidance = (self.lesson.guided_controller.snapshot(now=self.clock()) if self.transport.mode == "learn" and self.lesson.guided_controller else None)
        if not guidance or self.measurement.attempt_id is None:
            return
        if not guidance["completed"]:
            self.measurement.observe_guidance(guidance)
            return
        pending = self.take.pending
        if pending is None or pending.event.attempt_id != self.measurement.attempt_id:
            pending = self.lesson.prepare_decision("guided_completed", completed=True,
                assisted_count=guidance.get("assisted_count",0))
        try:
            self.take.seal_guided_preparation(
                pending,guidance=guidance,plan=self.lesson.plan,
                binding=self.lesson.decision_binding(),now=self.clock())
        except Exception:
            self.transport.freeze_after_fault(self.clock())
            self.notices.fault("Could not save the guided preparation",
                "Check storage, then Resume to save this same exposure.")
            raise
        self.lesson.finish_guided_preparation(remediation_active=pending.state.route.remediation_active)
        if pending.decision.next_exposure is not None:
            self.enter_selected_exposure(pending.decision.next_exposure)
        if pending.decision.message:
            self.lesson.flow_say(pending.decision.message)

    def enter_selected_exposure(self, selected, *, bump_revision: bool = True, reason=None):
        if selected is None:
            self.transport.stop_automatic()
            return
        if selected.mode == "learn":
            self.begin_learn(from_beat=selected.from_beat,
                              bump_revision=bump_revision,exposure=selected,reason=reason)
        elif selected.mode == "perform":
            self.exposure_workflows.prepare_perform(exposure=selected,reason=reason)
        else:
            self.exposure_workflows.prepare_practice(exposure=selected,reason=reason)

    def flow_execute(self, transition: practice_flow.Transition, *, reason=None) -> None:
        """Execute the selected course step; the session owns flow state."""
        effect = self.lesson.execute_flow(transition)
        if effect.step is practice_flow.Step.LISTEN:
            self.exposure_workflows.prepare_listen(reason=reason)
        elif effect.step is practice_flow.Step.FREE:
            self.lesson.set_course_guided(True)
            self.begin_learn(from_beat=0.0,reason=reason)
        elif effect.step is practice_flow.Step.TEMPO:
            self.exposure_workflows.prepare_practice(reason=reason)
        if effect.feedback:
            self.notices.feedback = effect.feedback
            self.notices.next_action = effect.next_action

    def flow_open(self, *, resumed: bool = False) -> None:
        """Open: a fresh piece starts with Listen, a resumed one in Free."""
        self.lesson.set_course_guided(True)
        self.transport.continue_course()
        # Even an opening Listen is a selected window. Closing before the
        # first Free note must still reopen that saved location in Free.
        self._save()
        self.flow_execute(self.lesson.flow_opening(self.lesson.plan,resumed=resumed))

    def begin_course_stage(self, *, bump_revision: bool = True,
                           explicit_learn: bool = False, effect=None,
                           reason=None):
        effect = self.lesson.manual_effect(
            "learn" if explicit_learn else "course_stage", effect=effect)
        selected = self.lesson.install_command(effect)
        if selected is not None:
            self.enter_selected_exposure(selected,bump_revision=bump_revision,reason=reason)

    def begin_learn(self, *, from_beat: float = 0.0, bump_revision: bool = True,
                     recovery: bool = False,
                     remediation: RemedialAssignment | None = None,
                     exposure=None, effect=None, reason=None):
        self.exposure_workflows.source()  # raises "Open a piece first"
        entry = self.lesson.flow_guided_entry(self.lesson.plan,
            recovery=recovery,simplified=remediation is not None)
        if entry is not None:
            self.flow_execute(entry,reason=reason)
            return
        shown = self.lesson.drawn_score
        selected = exposure or self.lesson.install_command(self.lesson.manual_effect(
            "learn",from_beat=from_beat,effect=effect))
        # Unchanged notes keep their revision: the drawn score stays (no
        # clear, no re-engraving). An aid always brings different notes.
        same_score = (remediation is None and bool(shown)
                      and shown == self.exposure_workflows.score.displayed_score(
                          learning=True, aid=None))
        # Command installation may select a different source variant/window.
        prepared = prepare_guided(self.exposure_workflows.source(),selected,
            revision=self.lesson.revision,bump_revision=bump_revision and not same_score,
            recovery=recovery,remediation=remediation,retry_range=self.take.retry_range)
        self.exposure_workflows.install(prepared,reason=reason)


class LessonNavigation:
    def __init__(self, *, lesson, notices, exposure_workflows, transport, take,
                 learner_progress, progress, lifecycle, course):
        self.lesson = lesson
        self.notices = notices
        self.exposure_workflows = exposure_workflows
        self.transport = transport
        self.take = take
        self.learner_progress = learner_progress
        self.progress = progress
        self.lifecycle = lifecycle
        self.course = course

    def _save(self) -> None:
        self.progress.save(self.lesson.plan, self.lesson.fingerprint)

    def learner_snapshot(self) -> dict:
        return self.learner_progress.snapshot(
            self.lesson.plan, fingerprint=self.lesson.fingerprint, mode=self.transport.mode,
            guided_range=self.lesson.guided_beat_range, course_guided=self.lesson.course_guided)

    def open_selected_measure(self, kwargs: dict, *, effect=None):
        effect = self.lesson.manual_effect(
            "open_at", values=kwargs, effect=effect)
        self.lifecycle.stop(reason="open_at")
        selected = self.lesson.install_command(effect)
        self.lesson.set_course_guided(selected.mode == "learn")
        self.lesson.select_opening(selected.from_beat)
        if selected.mode == "learn":
            self.course.begin_learn(
                from_beat=selected.from_beat,exposure=selected,reason="open_at")
        else:
            self.exposure_workflows.prepare_practice(exposure=selected,reason="open_at")
            self.transport.wait_for_player()
            self.notices.feedback = f"Ready to practise from measure {kwargs.get('bar')}"
            self.notices.next_action = "Press Start to play from the selected measure."

    def change_stage(self, action: str, kwargs: dict, *, effect=None):
        """Change the active lesson or tempo while preserving scoring state."""
        p=self.lesson.plan
        if not p:
            raise ValueError("Open a piece first")
        queued = effect
        change = (queued.event.manual
                  if queued is not None and queued.event.action == action
                  and queued.event.manual is not None
                  else prepare_stage_change(
                      p, action, kwargs))
        was_guided = self.transport.mode == "learn"
        guided_return = self.lesson.guided_return_context
        guided_retry_range = self.take.retry_range
        self.lifecycle.stop(reason=action)
        # Preserve the original ordering of the source opening reset.
        if action in ("select_step", "next", "previous"):
            self.lesson.select_opening(0.0)
        effect = (queued if queued is not None and queued.event.action == action
                  else self.lesson.prepare_decision(
                      "manual", manual=change, action=action, store=False))
        self.lesson.apply_progress(effect)
        self.take.command_applied()
        if action == "hand":
            self.lesson.select_opening(0.0)
        # Native notation is engraved in source coordinates: changing
        # only playback BPM must not invalidate the score/reload Godot.
        if not change.tempo_only:
            self.lesson.advance_revision()
        self.notices.feedback="Ready"
        self.notices.next_action="Start when you are ready."
        if was_guided:
            selected = effect.decision.next_exposure
            if selected is not None and selected.mode == "learn":
                recovery = change.tempo_only and guided_return is not None and guided_return[0] == p.identity
                if recovery:
                    self.take.restore_retry(guided_retry_range)
                self.course.begin_learn(
                from_beat=selected.from_beat,bump_revision=False,
                recovery=recovery,exposure=selected,reason=action)
            elif selected is not None:
                self.course.enter_selected_exposure(selected,reason=action)
        self.progress.save(self.lesson.plan, self.lesson.fingerprint)


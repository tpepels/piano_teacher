"""Execute selected lesson stages, guided exposures, navigation and course progress.

Only the registered lesson generator selects stages and tempo. The session
lifecycle and transport retain one physical/authorized take timeline.
"""
from __future__ import annotations
from ..music import Phrase
from ..measure_grid import phrase_grid
from ..remediation import RemedialAssignment
from . import practice_flow
from .exposure_preparation import prepare_guided
from .mistake_responses import resolve_mistake_policy


class LessonExecution:
    def __init__(self, *, lesson, notices,
                 exposure_workflows,
                 transport, attempt, learner_progress,
                 progress, lifecycle, recovery_streak,
                 attempt_settlement, measurement, library, clock):
        self.lesson = lesson
        self.notices = notices
        self.exposure_workflows = exposure_workflows
        self.transport = transport
        self.attempt = attempt
        self.learner_progress, self.progress = learner_progress, progress
        self.lifecycle, self.recovery_streak = lifecycle, recovery_streak
        self.attempt_settlement = attempt_settlement
        self.measurement, self.library = measurement, library
        self.clock = clock

    def _stop(self, *, reason=None, preserve_episode=False, persist_evidence=True) -> None:
        self.lifecycle.stop(reason=reason or "transition",
            preserve_episode=preserve_episode, persist_evidence=persist_evidence)

    def _save(self) -> None:
        self.progress.save(self.lesson.plan, self.lesson.fingerprint)

    def guided_unit(self) -> dict | None:
        return self.learner_progress.guided_unit(
            self.lesson.plan, mode=self.transport.mode, guided_range=self.lesson.guided_beat_range)

    def save_guided_preparation(self):
        guidance = (self.lesson.guided_controller.snapshot(now=self.clock()) if self.transport.mode == "learn" and self.lesson.guided_controller else None)
        if not guidance or self.measurement.attempt_id is None:
            return
        if not guidance["completed"]:
            self.measurement.observe_guidance(guidance)
            return
        pending = self.attempt_settlement.pending
        if pending is None or pending.event.attempt_id != self.measurement.attempt_id:
            pending = self.lesson.prepare_decision("guided_completed", completed=True,
                assisted_count=guidance.get("assisted_count",0))
        try:
            self.attempt_settlement.seal_guided_preparation(
                pending,guidance=guidance,plan=self.lesson.plan,
                binding=self.lesson.decision_binding(),now=self.clock(),
                policy=resolve_mistake_policy(
                    self.library.settings["mistake_response_strategy"]))
        except Exception:
            self.transport.freeze_after_fault(self.clock())
            self.notices.fault("Could not save the guided preparation",
                "Check storage, then Resume to save this same exposure.")
            raise
        self.lesson.finish_guided_preparation(remediation_active=pending.state.route.remediation_active)
        if pending.decision.next_exposure is not None:
            self.enter_selected_exposure(pending.decision.next_exposure)
        if pending.decision.message:
            self.flow_say(pending.decision.message)

    def learner_snapshot(self) -> dict:
        return self.learner_progress.snapshot(
            self.lesson.plan, fingerprint=self.lesson.fingerprint, mode=self.transport.mode,
            guided_range=self.lesson.guided_beat_range, course_guided=self.lesson.course_guided)

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

    def flow_active(self) -> bool:
        return self.lesson.flow_applies(self.lesson.plan,warmup=self.lesson.warmup)

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

    def flow_say(self, text: str) -> None:
        self.lesson.flow_say(text)

    def flow_state(self) -> dict:
        return self.lesson.flow_status(self.lesson.plan,self.transport.mode)

    def begin_course_stage(self, *, bump_revision: bool = True,
                           explicit_learn: bool = False, effect=None,
                           reason=None):
        effect = self.lesson.manual_effect(
            "learn" if explicit_learn else "course_stage", effect=effect)
        selected = self.lesson.install_command(effect)
        if selected is not None:
            self.enter_selected_exposure(selected,bump_revision=bump_revision,reason=reason)

    def skip_stage(self, reason, *, effect=None):
        effect = self.lesson.manual_effect(
            "skip_stage", values={"reason":reason}, effect=effect)
        self.learner_progress.mark_skipped(fingerprint=self.lesson.fingerprint, stage_key=self.lesson.plan.identity, reason=reason)
        self._stop(reason="skip_stage")
        selected = self.lesson.install_command(effect)
        self.reset_trouble()
        self.lesson.set_course_guided(True)
        self.enter_selected_exposure(selected,reason="skip_stage")
        self._save()

    def place_original(self, *, effect=None):
        if self.lesson.plan is None:
            raise ValueError("Open a piece first")
        effect = self.lesson.manual_effect(
            "place_original", effect=effect)
        key = effect.decision.next_exposure.stage_key
        candidate = next(step for step in self.lesson.plan.lesson_steps if step.key == key)
        self.learner_progress.mark_prior_steps_placed(self.lesson.plan, fingerprint=self.lesson.fingerprint, candidate=candidate)
        self._stop(reason="place_original")
        selected = self.lesson.install_command(effect)
        self.reset_trouble()
        self.lesson.set_course_guided(True)
        self.enter_selected_exposure(selected,reason="place_original")
        self._save()

    def valid_trouble_spots(self, *, stage_key: str | None = None) -> list[dict]:
        return self.lesson.valid_trouble_spots(stage_key=stage_key)

    def revisit_trouble(self, stage_key, start_beat, *, effect=None):
        effect = self.lesson.manual_effect(
            "revisit_trouble", from_beat=start_beat,
            values={"stage_key":stage_key}, effect=effect)
        self._stop(reason="revisit_trouble")
        selected = self.lesson.install_command(effect)
        self.reset_trouble()
        self.learner_progress.reactivate_trouble(fingerprint=self.lesson.fingerprint, stage_key=selected.stage_key)
        self.lesson.set_course_guided(True)
        grid = phrase_grid(self.lesson.plan.active_phrase,self.lesson.plan.piece.bar_boundaries)
        self.attempt.prepare_section(start=selected.from_beat,end=selected.end_beat,
            first_bar=self.lesson.plan.active_phrase.first_bar+grid.index(selected.from_beat),
            last_bar=self.lesson.plan.active_phrase.first_bar+grid.index(selected.end_beat)-1)
        self.begin_learn(from_beat=selected.from_beat,recovery=True,exposure=selected,
            reason="revisit_trouble")
        self._save()

    def reset_trouble(self):
        self.recovery_streak.clear()

    def display_phrase(self) -> Phrase:
        if self.lesson.plan is None:
            raise ValueError("Open a piece first")
        return self.lesson.guided_display_phrase(
            self.lesson.plan.active_phrase,self.lesson.plan.piece.bar_boundaries,
            active=self.transport.mode == "learn")

    def begin_learn(self, *, from_beat: float = 0.0, bump_revision: bool = True,
                     recovery: bool = False,
                     remediation: RemedialAssignment | None = None,
                     exposure=None, effect=None, reason=None):
        source = self.exposure_workflows.source()
        entry = self.lesson.flow_guided_entry(self.lesson.plan,
            warmup=source.warmup,recovery=recovery,simplified=remediation is not None)
        if entry is not None:
            self.flow_execute(entry,reason=reason)
            return
        selected = exposure or self.lesson.install_command(self.lesson.manual_effect(
            "learn",from_beat=from_beat,effect=effect))
        # Command installation may select a different source variant/window.
        prepared = prepare_guided(self.exposure_workflows.source(),selected,
            revision=self.lesson.revision,bump_revision=bump_revision,
            recovery=recovery,remediation=remediation,retry_range=self.attempt.retry_range)
        self.exposure_workflows.install(prepared,reason=reason)

    def review_retry(self, first_bar, last_bar, *, effect=None):
        effect = self.lesson.manual_effect(
            "review_retry",values={"first_bar":first_bar,"last_bar":last_bar},
            effect=effect)
        selected = self.lesson.install_command(effect)
        self.exposure_workflows.prepare_practice(exposure=selected,reason="review_retry")
        self.lesson.select_opening(selected.from_beat)
        self.attempt.prepare_section(start=self.lesson.opening_beat,
            end=selected.end_beat or self.lesson.plan.active_phrase.end-self.lesson.plan.active_phrase.start,
            first_bar=first_bar,last_bar=last_bar)
        self.transport.prepare_section_review()
        self.notices.feedback = f"Ready to repeat measures {first_bar}-{last_bar}"
        self.notices.next_action = "Press Start to practise this section; no mastery is awarded for a partial attempt."

    def practice_weak(self, *, effect=None):
        effect = self.lesson.manual_effect("practice_weak", effect=effect)
        selected = self.lesson.install_command(effect)
        self.exposure_workflows.prepare_practice(exposure=selected,reason="practice_weak")
        self.lesson.select_opening(selected.from_beat)
        self.attempt.prepare_section(start=self.lesson.opening_beat,
            end=selected.end_beat or self.lesson.plan.active_phrase.end-self.lesson.plan.active_phrase.start)
        self.transport.prepare_section_review()
        self.notices.next_action = "Press Start to practise this section; no mastery is awarded for a partial attempt."

    def seek_grid(self) -> tuple[float, ...] | None:
        if (self.lesson.plan is None or self.transport.mode not in ("learn", "practice", "perform")
                or not self.lesson.plan.piece.bar_boundaries):
            return None
        try:
            return phrase_grid(self.lesson.plan.active_phrase, self.lesson.plan.piece.bar_boundaries)
        except ValueError:
            return None

    def seek(self, bar, *, effect=None):
        # A seek must never guess a measure from synthetic/fallback bar
        # numbering. Validate original source boundaries *before* preparing
        # any command or cancelling a paused transport.
        if self.seek_grid() is None:
            raise ValueError("Seeking requires the original source measure grid")
        effect = self.lesson.manual_effect(
            "seek",values={"bar":bar},effect=effect)
        selected = self.lesson.install_command(effect)
        if selected.mode == "learn":
            self.begin_learn(from_beat=selected.from_beat,exposure=selected,reason="seek")
        else:
            self.exposure_workflows.prepare_practice(exposure=selected,reason="seek")
            self.transport.prepare_rewind(selected.from_beat)
            self.attempt.prepare_section(start=selected.from_beat,
                end=self.lesson.plan.active_phrase.end-self.lesson.plan.active_phrase.start,
                first_bar=bar,last_bar=self.lesson.plan.active_phrase.last_bar)
            self.notices.next_action = f"Get ready to play from bar {bar} at {selected.bpm} BPM."


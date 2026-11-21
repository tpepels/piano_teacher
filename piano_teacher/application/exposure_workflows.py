"""Prepare a selected lesson's guided, timed and listening sources.

Preparation is a consequence of the one accepted teaching decision.
Playback authorization remains the responsibility of PlaybackCoordinator;
this service does not open a timed take on its own.
"""
from __future__ import annotations
from .exposure_preparation import ExposureSource, prepare_timed, prepare_listen


class ExposureWorkflows:
    def __init__(self, *, source_identity, flow_session, teaching_decisions,
                 session_commands, guided_session, attempt, tempo_map_cache,
                 playback_session, listen, notices, installer):
        self.source_identity = source_identity
        self.flow_session = flow_session
        self.teaching_decisions = teaching_decisions
        self.session_commands = session_commands
        self.guided_session = guided_session
        self.attempt = attempt
        self.tempo_map_cache = tempo_map_cache
        self.playback_session = playback_session
        self.listen = listen
        self.notices = notices
        self.installer = installer

    def source(self) -> ExposureSource:
        selected = self.source_identity.plan
        if selected is None:
            raise ValueError("Open a piece first")
        return ExposureSource(
            selected.identity, selected.active_variant,
            selected.piece.bar_boundaries, selected.piece.time_signatures,
            self.source_identity.warmup,
            self.flow_session.active(selected, warmup=self.source_identity.warmup))

    def prepare_practice(self, *, exposure=None):
        selected_plan = self.source_identity.plan
        if selected_plan is None:
            raise ValueError("Open a piece first")
        effect = (None if exposure is not None
                  else self.teaching_decisions.manual_effect("practice"))
        selected = exposure or self.teaching_decisions.install_command(effect)
        entry = self.flow_session.tempo_entry(
            selected_plan, warmup=self.source_identity.warmup, bpm=selected.bpm)
        if entry.active:
            self.session_commands.prepare_exposure(selected)
        if entry.clear_guided_return:
            self.guided_session.discard_return()
        self.installer.apply(prepare_timed(
            self.source(), selected,
            mode="practice", revision=self.source_identity.revision,
            return_context=self.guided_session.return_context,
            retry_range=self.attempt.retry_range))

    def prepare_listen(self) -> None:
        selected_plan = self.source_identity.plan
        if selected_plan is None:
            raise ValueError("Open a piece first")
        self.teaching_decisions.install_command(
            self.teaching_decisions.manual_effect("listen"))
        self.installer.apply(prepare_listen(
            self.source(), revision=self.source_identity.revision,
            bpm=selected_plan.bpm,
            tempo_map=self.tempo_map_cache.get(
                selected_plan.active_stage, selected_plan.bpm)))

    def prepare_perform(self, *, scope: str = "current", exposure=None) -> None:
        if self.source_identity.plan is None:
            raise ValueError("Open a piece first")
        effect = (None if exposure is not None else
                  self.teaching_decisions.manual_effect(
                      "perform", values={"scope":scope}))
        selected = exposure or self.teaching_decisions.install_command(effect)
        self.installer.apply(prepare_timed(
            self.source(), selected,
            mode="perform", revision=self.source_identity.revision))

    def apply_listen_failure(self) -> None:
        failure = self.listen.take_failure()
        if failure is not None:
            self.playback_session.wait_for_player()
            self.notices.publish(failure, failure)

"""Enter a selected lesson's guided, timed and listening exposures.

Preparation (exposure_preparation) is a pure consequence of the one
accepted teaching decision. install() applies it in a fixed order: save
resume, interrupt/cancel the prior take, publish the exact revision, bind
guided targets and capture new evidence. Playback authorization remains
PlaybackCoordinator's; this service never opens a timed take itself.
"""
from __future__ import annotations
from .exposure_preparation import (
    ExposureSource, prepare_timed, prepare_listen,
    GuidedPreparation, TimedPreparation, ListenPreparation)


class ExposureWorkflows:
    def __init__(self, *, source_identity, lesson_cursor, flow_session,
                 teaching_decisions, guided_session, attempt, tempo_map_cache,
                 transport, listen, notices, lifecycle,
                 learner_progress, progress, score_state_publisher,
                 midi, evidence_context, clock):
        self.source_identity = source_identity
        self.lesson_cursor = lesson_cursor
        self.flow_session = flow_session
        self.teaching_decisions = teaching_decisions
        self.guided_session = guided_session
        self.attempt = attempt
        self.tempo_map_cache = tempo_map_cache
        self.transport = transport
        self.listen = listen
        self.notices = notices
        self.lifecycle = lifecycle
        self.learner_progress = learner_progress
        self.progress = progress
        self.score_state_publisher = score_state_publisher
        self.midi = midi
        self.evidence_context = evidence_context
        self.clock = clock

    def source(self) -> ExposureSource:
        selected = self.source_identity.plan
        if selected is None:
            raise ValueError("Open a piece first")
        return ExposureSource(
            selected.identity, selected.active_variant,
            selected.piece.bar_boundaries, selected.piece.time_signatures,
            self.source_identity.warmup,
            self.flow_session.active(selected, warmup=self.source_identity.warmup))

    def prepare_practice(self, *, exposure=None, effect=None, reason="transition"):
        selected_plan = self.source_identity.plan
        if selected_plan is None:
            raise ValueError("Open a piece first")
        effect = (None if exposure is not None
                  else self.teaching_decisions.manual_effect("practice", effect=effect))
        selected = exposure or self.teaching_decisions.install_command(effect)
        entry = self.flow_session.tempo_entry(
            selected_plan, warmup=self.source_identity.warmup, bpm=selected.bpm)
        if entry.clear_guided_return:
            self.guided_session.discard_return()
        self.install(prepare_timed(
            self.source(), selected,
            mode="practice", revision=self.source_identity.revision,
            return_context=self.guided_session.return_context,
            retry_range=self.attempt.retry_range), reason=reason)

    def prepare_listen(self, *, effect=None, reason="transition") -> None:
        selected_plan = self.source_identity.plan
        if selected_plan is None:
            raise ValueError("Open a piece first")
        self.teaching_decisions.install_command(
            self.teaching_decisions.manual_effect("listen", effect=effect))
        self.install(prepare_listen(
            self.source(), revision=self.source_identity.revision,
            bpm=selected_plan.bpm,
            tempo_map=self.tempo_map_cache.get(
                selected_plan.active_stage, selected_plan.bpm)), reason=reason)

    def prepare_perform(self, *, scope: str = "current", exposure=None,
                        effect=None, reason="transition") -> None:
        if self.source_identity.plan is None:
            raise ValueError("Open a piece first")
        effect = (None if exposure is not None else
                  self.teaching_decisions.manual_effect(
                      "perform", values={"scope":scope}, effect=effect))
        selected = exposure or self.teaching_decisions.install_command(effect)
        self.install(prepare_timed(
            self.source(), selected,
            mode="perform", revision=self.source_identity.revision), reason=reason)

    def apply_listen_failure(self) -> None:
        failure = self.listen.take_failure()
        if failure is not None:
            self.transport.wait_for_player()
            self.notices.publish(failure, failure)

    def install(self, prepared:
              GuidedPreparation | TimedPreparation | ListenPreparation,
              *, reason: str | None = None) -> None:
        action_reason = reason or "transition"
        if isinstance(prepared, GuidedPreparation):
            fragment = prepared.fragment
            self.learner_progress.save_resume(
                fingerprint=self.source_identity.fingerprint,
                stage_key=prepared.source.stage_key,
                unit=self.learner_progress.guided_unit(
                    self.source_identity.plan, mode="learn",
                    guided_range=fragment.beat_range))
            self.progress.save(
                self.source_identity.plan, self.source_identity.fingerprint)
            self.lifecycle.stop(
                reason=prepared.stop_reason or action_reason,
                preserve_episode=prepared.recovery)
            self.score_state_publisher.reset_guided()
            self.attempt.assign_remediation(prepared.remediation)
            if prepared.recovery:
                self.attempt.restore_retry(prepared.retry_range)
            self.transport.select_exposure(
                mode="learn", automatic=False, awaited_revision=None)
            self.guided_session.select(
                fragment, stage_key=prepared.source.stage_key,
                recovery=prepared.recovery)
            self.source_identity.publish_revision(prepared.revision)
            self.transport.open_take()
            self.guided_session.bind_selected(
                revision=prepared.revision,
                now=self.clock(), connected=self.midi.connected)
            self.transport.await_score(prepared.revision)
            self.transport.capture_guided_start(
                self.evidence_context.build(
                    scope="guided",
                    start=fragment.start_beat, end=fragment.end_beat))
        else:
            timed = isinstance(prepared, TimedPreparation)
            self.lifecycle.stop(
                reason=("reintegration" if timed and prepared.mode == "practice"
                        else action_reason),
                preserve_episode=timed and prepared.preserve_episode)
            if not timed or prepared.mode == "practice":
                self.transport.select_opening(
                    prepared.from_beat if timed else 0.0)
            if timed:
                self.lesson_cursor.select_opening(prepared.from_beat)
                self.attempt.prepare_timed_exposure(prepared)
                if prepared.return_context is not None:
                    self.transport.prepare_rewind(prepared.from_beat)
                    self.guided_session.select_timed_return(prepared.return_context)
            self.guided_session.clear_selection()
            self.source_identity.publish_revision(prepared.revision)
            self.transport.select_exposure(
                mode=prepared.mode if timed else "listen", automatic=False,
                awaited_revision=(prepared.awaiting_score if timed
                                  else prepared.revision))
        self.notices.publish(prepared.feedback, prepared.next_action)
        if isinstance(prepared, ListenPreparation):
            self.listen.prepare(prepared.selection)

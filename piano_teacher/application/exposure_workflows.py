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
    def __init__(self, *, lesson, take, score, transport, listen, notices,
                          lifecycle, learner_progress, progress, midi_input,
                          evidence_context, clock):
        self.lesson = lesson



        self.take = take
        self.score = score
        self.transport = transport
        self.listen = listen
        self.notices = notices
        self.lifecycle = lifecycle
        self.learner_progress = learner_progress
        self.progress = progress
        self.midi_input = midi_input
        self.evidence_context = evidence_context
        self.clock = clock

    def source(self) -> ExposureSource:
        selected = self.lesson.plan
        if selected is None:
            raise ValueError("Open a piece first")
        return ExposureSource(
            selected.identity, selected.active_variant,
            selected.piece.bar_boundaries, selected.piece.time_signatures,
            self.lesson.warmup,
            self.lesson.flow_applies(selected, warmup=self.lesson.warmup))

    def prepare_practice(self, *, exposure=None, effect=None, reason="transition"):
        selected_plan = self.lesson.plan
        if selected_plan is None:
            raise ValueError("Open a piece first")
        effect = (None if exposure is not None
                  else self.lesson.manual_effect("practice", effect=effect))
        selected = exposure or self.lesson.install_command(effect)
        entry = self.lesson.flow_tempo_entry(
            selected_plan, warmup=self.lesson.warmup, bpm=selected.bpm)
        if entry.clear_guided_return:
            self.lesson.discard_guided_return()
        self.install(prepare_timed(
            self.source(), selected,
            mode="practice", revision=self.lesson.revision,
            return_context=self.lesson.guided_return_context,
            retry_range=self.take.retry_range), reason=reason)

    def prepare_listen(self, *, effect=None, reason="transition") -> None:
        selected_plan = self.lesson.plan
        if selected_plan is None:
            raise ValueError("Open a piece first")
        self.lesson.install_command(
            self.lesson.manual_effect("listen", effect=effect))
        self.install(prepare_listen(
            self.source(), revision=self.lesson.revision,
            bpm=selected_plan.bpm,
            tempo_map=self.score.tempo_map(
                selected_plan.active_stage, selected_plan.bpm)), reason=reason)

    def prepare_perform(self, *, scope: str = "current", exposure=None,
                        effect=None, reason="transition") -> None:
        if self.lesson.plan is None:
            raise ValueError("Open a piece first")
        effect = (None if exposure is not None else
                  self.lesson.manual_effect(
                      "perform", values={"scope":scope}, effect=effect))
        selected = exposure or self.lesson.install_command(effect)
        self.install(prepare_timed(
            self.source(), selected,
            mode="perform", revision=self.lesson.revision), reason=reason)

    def finish_listen(self, now: float) -> bool:
        """End a running Listen example whose audio has finished."""
        if not (self.transport.running
                and self.listen.finished(now=now, run_at=self.transport.run_at)):
            return False
        self.transport.finish_take()
        self.notices.feedback = "Example complete"
        self.notices.next_action = (
            "Choose Learn to find the notes, or Practice to play the rhythm.")
        return True

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
                fingerprint=self.lesson.fingerprint,
                stage_key=prepared.source.stage_key,
                unit=self.learner_progress.guided_unit(
                    self.lesson.plan, mode="learn",
                    guided_range=fragment.beat_range))
            self.progress.save(
                self.lesson.plan, self.lesson.fingerprint)
            self.lifecycle.stop(
                reason=prepared.stop_reason or action_reason,
                preserve_episode=prepared.recovery)
            self.score.reset_guided_score()
            self.take.assign_remediation(prepared.remediation)
            if prepared.recovery:
                self.take.restore_retry(prepared.retry_range)
            self.transport.select_exposure(
                mode="learn", automatic=False, awaited_revision=None)
            self.lesson.select_guided(
                fragment, stage_key=prepared.source.stage_key,
                recovery=prepared.recovery)
            self.lesson.publish_revision(prepared.revision)
            self.transport.open_take()
            self.lesson.bind_guided_selection(
                revision=prepared.revision,
                now=self.clock(), connected=self.midi_input.connected)
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
                self.lesson.select_opening(prepared.from_beat)
                self.take.prepare_timed_exposure(prepared)
                if prepared.return_context is not None:
                    self.transport.prepare_rewind(prepared.from_beat)
                    self.lesson.select_timed_return(prepared.return_context)
            self.lesson.clear_guided_selection()
            self.lesson.publish_revision(prepared.revision)
            self.transport.select_exposure(
                mode=prepared.mode if timed else "listen", automatic=False,
                awaited_revision=(prepared.awaiting_score if timed
                                  else prepared.revision))
        self.notices.publish(prepared.feedback, prepared.next_action)
        if isinstance(prepared, ListenPreparation):
            self.listen.prepare(prepared.selection)

"""Apply already-selected guided/timed/Listen exposure effects.

Source selection is performed by the registered lesson decision owner.
Installation preserves the order: save resume, interrupt/cancel prior take,
publish exact revision, bind guided targets and capture the new evidence.
No engine reference, second lesson decision or alternative playback gate.
"""
from __future__ import annotations
from .exposure_preparation import GuidedPreparation, TimedPreparation, ListenPreparation


class ExposureInstaller:
    def __init__(self, *, source_identity, lesson_cursor, notices, lifecycle,
                 learner_progress, progress, score_state_publisher,
                 attempt, playback_session, guided_session, visual_transport,
                 midi, listen, evidence_context, session_commands, clock):
        self.source_identity = source_identity
        self.lesson_cursor = lesson_cursor
        self.notices = notices
        self.lifecycle = lifecycle
        self.learner_progress = learner_progress
        self.progress = progress
        self.score_state_publisher = score_state_publisher
        self.attempt = attempt
        self.playback_session = playback_session
        self.guided_session = guided_session
        self.visual_transport = visual_transport
        self.midi = midi
        self.listen = listen
        self.evidence_context = evidence_context
        self.session_commands = session_commands
        self.clock = clock

    def apply(self, prepared:
              GuidedPreparation | TimedPreparation | ListenPreparation) -> None:
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
                reason=prepared.stop_reason or self.session_commands.action_reason,
                preserve_episode=prepared.recovery)
            self.score_state_publisher.reset_guided()
            self.attempt.assign_remediation(prepared.remediation)
            if prepared.recovery:
                self.attempt.restore_retry(prepared.retry_range)
            self.playback_session.select_exposure(
                mode="learn", automatic=False, awaited_revision=None)
            self.guided_session.select(
                fragment, stage_key=prepared.source.stage_key,
                recovery=prepared.recovery)
            self.source_identity.publish_revision(prepared.revision)
            self.playback_session.open_take()
            self.guided_session.bind_selected(
                revision=prepared.revision,
                now=self.clock(), connected=self.midi.connected)
            self.playback_session.await_score(prepared.revision)
            self.playback_session.capture_guided_start(
                self.evidence_context.build(
                    scope="guided",
                    start=fragment.start_beat, end=fragment.end_beat))
        else:
            timed = isinstance(prepared, TimedPreparation)
            self.lifecycle.stop(
                reason=("reintegration" if timed and prepared.mode == "practice"
                        else self.session_commands.action_reason),
                preserve_episode=timed and prepared.preserve_episode)
            if not timed or prepared.mode == "practice":
                self.visual_transport.select_opening(
                    prepared.from_beat if timed else 0.0)
            if timed:
                self.lesson_cursor.select_opening(prepared.from_beat)
                self.attempt.prepare_timed_exposure(prepared)
                if prepared.return_context is not None:
                    self.visual_transport.prepare_rewind(prepared.from_beat)
                    self.guided_session.select_timed_return(prepared.return_context)
            self.guided_session.clear_selection()
            self.source_identity.publish_revision(prepared.revision)
            self.playback_session.select_exposure(
                mode=prepared.mode if timed else "listen", automatic=False,
                awaited_revision=(prepared.awaiting_score if timed
                                  else prepared.revision))
        self.notices.publish(prepared.feedback, prepared.next_action)
        if isinstance(prepared, ListenPreparation):
            self.listen.prepare(prepared.selection)

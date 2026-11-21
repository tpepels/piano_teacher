"""Exact future-source preload and admitted successor-asset handshake.

TeachingContinuation owns immutable future identities. Acknowledgement may
release only that preloaded revision's settled feedback; no new lesson
decision or alternate notation stream is created here.
"""
from __future__ import annotations
from .score_artifacts import ScoreSelection
from .teaching_continuation import PreloadedFeedbackSource


class ScorePreloadWorkflow:
    def __init__(self, *, source_identity, lock, playback_session,
                 teaching_continuation, attempt_settlement,
                 transport_timing, completion_continuations):
        self.source_identity, self.lock = source_identity, lock
        self.playback_session, self.teaching_continuation = playback_session, teaching_continuation
        self.attempt_settlement, self.transport_timing = attempt_settlement, transport_timing
        self.completion_continuations = completion_continuations

    def decided_selection(self):
        if not self.playback_session.auto:
            return None
        return self.teaching_continuation.selection(self.attempt_settlement.pending,
            revision=self.source_identity.revision,fingerprint=self.source_identity.fingerprint)

    def next_selection(self, *, offset: int = 1) -> tuple[ScoreSelection, int] | None:
        if self.source_identity.plan is None or self.source_identity.warmup or self.playback_session.mode != "practice":
            return None
        decided = self.decided_selection() if offset == 1 else None
        return self.teaching_continuation.choose_ahead(
            self.source_identity.plan,fingerprint=self.source_identity.fingerprint,revision=self.source_identity.revision,
            offset=offset,decided=decided)

    def next_stage_score(self) -> bytes:
        with self.lock:
            return self.teaching_continuation.ensure_next(
                self.next_selection())

    def report_preload_failure(self, *, fingerprint: str, step_number: int,
                               revision: int, error: str) -> dict:
        with self.lock:
            return self.teaching_continuation.report_native_failure(
                self.next_selection(),fingerprint=fingerprint,
                step_number=step_number,revision=revision,error=error)

    def acknowledge_preloaded_stage(self, *, stage_key: str,
                                    revision: int) -> dict:
        with self.lock:
            accepted = self.teaching_continuation.acknowledge_stage(
                self.next_selection(),stage_key=stage_key,revision=revision)
            source = (PreloadedFeedbackSource(
                self.source_identity.plan.active_phrase.sounding_end-self.source_identity.plan.active_phrase.start,
                self.source_identity.plan.bpm,self.transport_timing.active_tempo_map()) if self.source_identity.plan is not None else None)
            released_at = self.playback_session.activate_preloaded_feedback(source,
                revision=self.source_identity.revision,fingerprint=self.source_identity.fingerprint)
            if released_at is not None:
                self.completion_continuations.advance_pending_feedback(released_at)
            self.teaching_continuation.warm_more(
                self.next_selection(offset=2))
            return accepted


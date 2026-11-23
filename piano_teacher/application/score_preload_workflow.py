"""Exact future-source preload and admitted successor-asset handshake.

TeachingContinuation owns immutable future identities. Acknowledgement may
release only that preloaded revision's settled feedback; no new lesson
decision or alternate notation stream is created here.
"""
from __future__ import annotations
from .score_artifacts import ScoreSelection
from .playback_facts import PreloadedFeedbackSource


class ScorePreloadWorkflow:
    def __init__(self, *, lesson, lock, transport, teaching_continuation, take,
                          transport_timing, completion_continuations):
        self.lock = lock
        self.lesson = lesson
        self.teaching_continuation = teaching_continuation
        self.transport = transport
        self.transport_timing = transport_timing
        self.take = take
        self.completion_continuations = completion_continuations

    def decided_selection(self):
        if not self.transport.auto:
            return None
        return self.teaching_continuation.selection(self.take.pending,
            revision=self.lesson.revision,fingerprint=self.lesson.fingerprint)

    def next_selection(self, *, offset: int = 1) -> tuple[ScoreSelection, int] | None:
        if self.lesson.plan is None or self.lesson.warmup or self.transport.mode != "practice":
            return None
        decided = self.decided_selection() if offset == 1 else None
        return self.teaching_continuation.choose_ahead(
            self.lesson.plan,fingerprint=self.lesson.fingerprint,revision=self.lesson.revision,
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
                self.lesson.plan.active_phrase.sounding_end-self.lesson.plan.active_phrase.start,
                self.lesson.plan.bpm,self.transport_timing.active_tempo_map()) if self.lesson.plan is not None else None)
            released_at = self.transport.activate_preloaded_feedback(source,
                revision=self.lesson.revision,fingerprint=self.lesson.fingerprint)
            if released_at is not None:
                self.completion_continuations.advance_pending_feedback(released_at)
            self.teaching_continuation.warm_more(
                self.next_selection(offset=2))
            return accepted


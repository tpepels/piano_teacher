"""Source-bound live assessment publication and canonical note feedback facts.

All grading delegates to the existing configured AssessmentService policy.
Results are published by LiveAssessmentPublisher and never re-assigned by
a second matcher or another musical-time source.
"""
from __future__ import annotations
from ..live_feedback import live_scope


class LiveFeedbackWorkflows:
    def __init__(self, *, lesson, transport, score, policy_registry, library,
                          take, live_assessment, transport_timing, clock):
        self.lesson = lesson
        self.transport = transport
        self.score = score
        self.policy_registry = policy_registry
        self.library, self.live_assessment = library, live_assessment
        self.take = take
        self.transport_timing, self.clock = transport_timing, clock

    def feedback_take(self) -> dict:
        """Immutable identity of the take that the next feedback belongs to."""
        return {"piece_fingerprint": self.lesson.fingerprint or "",
                "revision": int(self.lesson.revision),
                "transport_id": int(self.transport.transport_id), "mode": self.transport.mode,
                "release_advisory": not self.library.settings["grade_note_holds"],
                "graded": (not self.transport.preview_only
                           and self.transport.mode in ("practice", "perform"))}

    def latest_marks(self, _elapsed_seconds: float) -> list[dict]:
        """The marks last published for the running take (none otherwise)."""
        return (list(self.live_assessment.latest_marks)
                if self.transport.running else [])

    def publish_frozen(self, marks) -> None:
        """Publish marks frozen at a rolling checkpoint (not yet final)."""
        self.live_assessment.publish(marks, self.feedback_take())

    def publish_final(self, marks) -> None:
        """Publish a completed take's settled grades before any successor."""
        self.live_assessment.publish(marks, self.feedback_take(), final=True)

    def publish_live(self) -> None:
        """Publish the incremental assessment continuously during playback.

        Uses the same _live_feedback grading call as every other consumer;
        only new or changed per-note results enter the feedback event log.
        """
        if (not self.transport.running or self.transport.preview_only
                or self.transport.mode not in ("practice", "perform")):
            # No running graded take: never carry the previous take's marks.
            self.live_assessment.clear()
            return
        if self.transport.paused:
            return
        elapsed = self.transport_timing.musical_seconds(self.clock())
        marks = self.live_feedback(elapsed)
        scope, _ = live_scope(self.lesson.plan.active_phrase,
            from_beat=self.transport.play_from_beat,elapsed_seconds=elapsed,
            bpm=self.lesson.plan.bpm,tempo=self.transport_timing.active_tempo_map())
        self.live_assessment.publish(marks, self.feedback_take(),scope_start_beat=scope)

    def live_feedback(self, elapsed_seconds: float) -> list[dict]:
        """Read the current cached source and ask the single grading owner."""
        plan = self.lesson.plan
        if plan is None or self.transport.preview_only or not self.transport.running:
            return []
        engraved = self.score.current_artifacts.cached_layout(self.score.selection())
        if engraved is None:
            return []
        return self.policy_registry.grading.live_projection(
            plan.active_phrase, hand=plan.hand, bpm=plan.bpm,
            played=self.take.recorder.presses if self.take.recorder else (),
            from_beat=self.transport.play_from_beat,
            elapsed_seconds=elapsed_seconds,
            bar_boundaries=plan.piece.bar_boundaries,
            layout=engraved.layout, tempo=self.transport_timing.active_tempo_map())


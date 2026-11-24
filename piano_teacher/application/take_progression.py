"""Progress of a running graded take on each tick.

Checkpoints the played prefix at each bar boundary and hands a completed
take to TakeCompletion.
"""
from __future__ import annotations
from .attempt_progression import AttemptTick


class TakeProgression:
    def __init__(self, *, lesson, transport, take, midi_input,
                 transport_timing, attempt_progression, completion, notices,
                 clock):
        self.lesson = lesson
        self.transport = transport
        self.take = take
        self.midi_input = midi_input
        self.transport_timing = transport_timing
        self.attempt_progression = attempt_progression
        self.completion = completion
        self.notices = notices
        self.clock = clock

    def checkpoint(self, boundary: float) -> None:
        """Persist the played prefix at a bar boundary."""
        try:
            self.take.checkpoint_boundary(
                self.take.recorder.presses if self.take.recorder else (),
                boundary=boundary)
        except Exception:
            self.transport.freeze_after_fault(self.clock())
            self.notices.fault("Could not save the recording checkpoint",
                "Check storage, then Resume to retry this boundary.")
            raise

    def advance(self, now: float) -> bool:
        """Inspect the running take; return whether a follow-up is queued."""
        if (self.transport.running and self.transport.grading_is_frozen(
                    now,grading_after=self.midi_input.resume_grading_after)):
            # The canonical recorder and live-assessment clock stand at the
            # paused source position. Do not checkpoint or complete the take
            # during the admitted continuation's reading/count-in lead.
            return False
        phrase = self.lesson.plan.active_phrase
        score_beat = self.transport.play_from_beat + max(
            0.0, self.transport_timing.elapsed_beat(now-self.transport.run_at))

        step = self.attempt_progression.inspect(AttemptTick(
            phrase=phrase, boundaries=self.lesson.plan.piece.bar_boundaries,
            now=now, score_beat=score_beat, from_beat=self.transport.play_from_beat,
            run_at=self.transport.run_at, next_boundary=self.transport.next_boundary_beat,
            auto=self.transport.auto, mode=self.transport.mode,
            bpm=self.lesson.plan.bpm, gap_beats=self.transport.visual_gap_beats),
            self.checkpoint, self.transport_timing.elapsed_seconds)
        self.transport.advance_boundary(step.next_boundary)
        followup = False
        if step.action == "complete":
            followup = self.completion.complete_take(phrase, step.ending,
                phrase.sounding_end-phrase.start, step.duration, now)
        return followup

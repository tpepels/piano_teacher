"""Progress of a running graded take on each tick.

Replays an admitted rolling recovery once, inspects the take's next
boundary (rolling checkpoint, missed attacks, completion) and hands a
completed take to TakeCompletion.
"""
from __future__ import annotations
from .playback_facts import TimedTakeSource
from .attempt_progression import AttemptTick


class TakeProgression:
    def __init__(self, *, lesson, transport, take, midi_input,
                 transport_timing, attempt_progression, rolling_recovery,
                 completion, lesson_execution):
        self.lesson = lesson
        self.transport = transport
        self.take = take
        self.midi_input = midi_input
        self.transport_timing = transport_timing
        self.attempt_progression = attempt_progression
        self.rolling_recovery = rolling_recovery
        self.completion = completion
        self.lesson_execution = lesson_execution

    def replay_rolling(self, now: float) -> bool:
        """Replay an admitted rolling recovery; True when it consumed the tick."""
        # A rolling boundary is admitted once. A failed presentation must
        # replay the original receipt before any rewind/next-boundary branch
        # can consume this tick. Still honor physical score admission: it may
        # already be awaiting an external attestation and must not be
        # disturbed by a duplicate transport effect.
        rolling = self.take.rolling_record
        if (rolling is not None and rolling.transition is not None
                and self.transport.mode == "practice"
                and self.transport.running
                and not self.transport.paused
                and self.transport.intent is None):
            self.rolling_recovery.apply_rolling_recovery(
                rolling.decision, rolling.phrase, rolling.grid,
                rolling.score_beat, now)
            return True
        return False

    def advance(self, now: float) -> bool:
        """Inspect the running take; return whether a follow-up is queued."""
        if (self.transport.running and self.transport.grading_is_frozen(
                    now,grading_after=self.midi_input.resume_grading_after)):
            # The canonical recorder and live-assessment clock stand at the
            # paused source position. Do not inspect rolling checkpoints,
            # missed attacks, completion or recovery during the admitted
            # continuation's reading/count-in lead.
            return False
        phrase = self.lesson.plan.active_phrase
        score_beat = self.transport.play_from_beat + max(
            0.0, self.transport_timing.elapsed_beat(now-self.transport.run_at))

        step = self.attempt_progression.inspect(AttemptTick(
            phrase=phrase, boundaries=self.lesson.plan.piece.bar_boundaries,
            now=now, score_beat=score_beat, from_beat=self.transport.play_from_beat,
            run_at=self.transport.run_at, next_boundary=self.transport.next_boundary_beat,
            review_end=self.take.review_end_beat, preview=self.transport.preview_only,
            auto=self.transport.auto, mode=self.transport.mode,
            bpm=self.lesson.plan.bpm, gap_beats=self.transport.visual_gap_beats),
            self.rolling_recovery.assess_rolling_boundary, self.transport_timing.elapsed_seconds,
            exact_repeats=self.lesson_execution.flow_active())
        self.transport.advance_boundary(step.next_boundary)
        followup = False
        if step.action == "recovery":
            self.rolling_recovery.apply_rolling_recovery(
                step.recovery, phrase, step.grid, score_beat, now)
        elif step.action == "complete":
            followup = self.completion.complete_take(phrase, step.ending,
                phrase.sounding_end-phrase.start, step.duration, now)
            self.transport.refloor_fresh_announcement(TimedTakeSource(
                self.lesson.plan.active_phrase,self.lesson.plan.piece.bar_boundaries,
                self.lesson.plan.piece.time_signatures,self.lesson.plan.bpm,
                self.transport.visual_gap_beats),
                physical_rest_enabled=self.transport.short_rest is not None)
        return followup

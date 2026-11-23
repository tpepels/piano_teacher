"""Everything that happens immediately after a take ends.

An ungraded preview repeats; a graded take is assessed by TakeGrading and
its immediately settled consequence (policy response, performance,
section or partial-recovery review, selected exposure) is applied here.
A full passage is handed to SettlementContinuation, which settles it at
its durable successor boundary.
"""
from __future__ import annotations
from ..lesson_settings import SETTINGS
from ..music import Phrase
from .passage_outcome_presenter import performance_next_action


class TakeCompletion:
    def __init__(self, *, lesson, notices, take, transport, transport_timing,
                 timed_playback, selected_recovery, lesson_execution,
                 grading, settlement):
        self.lesson = lesson
        self.notices = notices
        self.take = take
        self.transport = transport
        self.transport_timing = transport_timing
        self.timed_playback = timed_playback
        self.selected_recovery = selected_recovery
        self.lesson_execution = lesson_execution
        self.grading = grading
        self.settlement = settlement

    def complete_take(self, phrase: Phrase, ending: float,
                          total_beats: float, duration: float, now: float) -> bool:
        """Apply post-performance state after the score's settlement interval.

        Called from PracticeSession's locked event drain. Assessment
        and grading occur only after a completed non-preview take.
        Returns whether another same-tick transition must be queued.
        """
        self.transport.record_take_end(
            at=self.transport.run_at + duration,
            bpm=self.lesson.plan.bpm)
        if self.transport.preview_only:
            # Disconnected MIDI: repeat as an ungraded preview, never create
            # fake notes, misses, accepted passes or mastery.
            self.take.finish_preview()
            self.transport.finish_take()
            self.transport.schedule_preview_repeat(
                source_seconds=duration,source_bpm=self.lesson.plan.bpm,
                presentation_bpm=self.transport_timing.presentation_bpm(),
                rest_measurement=self.transport_timing.collect_rest_measurement(
                    from_beat=0.0,
                    source_end=self.transport.run_at+duration),
                now=now,reading_horizon_beats=self.transport.continuous_horizon_beats)
            self.notices.feedback = "Timing preview - repeating after one empty measure"
            self.notices.next_action = "Connect your MIDI piano to earn progress."
            # The next preview must be admitted during the rest, not at
            # the previous retry deadline after its count-in is over.
            self.timed_playback.continue_at(self.transport.next_at,
                from_beat=0.0)
            return False
        completed_visual = self.transport_timing.visual_motion(now)[0]
        completed = self.grading.grade(phrase, ending, now)
        result = completed.assessed.result
        self.notices.feedback = completed.assessed.feedback
        if not self.apply_focused(
                completed.effect, phrase=phrase, result=result, now=now,
                visual_from=completed_visual):
            return self.settlement.finish_full_passage(result,total_beats,duration,now)
        return False

    def apply_focused(self, effect, *, phrase, result, now: float,
                      visual_from: float) -> bool:
        """Apply one immediately settled focused/performance consequence.

        Returns False for a full passage, whose consequence is applied by
        dispatch_effect only after its durable successor boundary.
        """
        if effect.action == "response":
            self.selected_recovery.apply_policy_response(
                effect.response,now=now,visual_from=visual_from)
        elif effect.action == "perform":
            self.finish_performance_review(phrase,result)
        elif effect.action == "section_review":
            self.finish_section_review(result)
        elif effect.action == "stop_review":
            self.transport.halt_continuation()
            self.notices.next_action = "Review this section before starting another take."
        elif effect.action == "exposure":
            self.lesson_execution.enter_selected_exposure(effect.exposure)
        elif effect.action == "partial_recovery":
            self.finish_partial_recovery(result,now,exposure=effect.exposure)
        elif effect.action == "full_passage":
            return False
        else:
            raise ValueError(f"Unknown completion consequence {effect.action!r}")
        return True


    def finish_performance_review(self, phrase: Phrase, result):
        """Publish review only after its evidence and source feedback commit."""
        self.notices.next_action = performance_next_action(
            warmup=self.lesson.warmup,summary=self.take.performance_summary)
        self.transport.stop_automatic()

    def finish_section_review(self, result):
        """Complete finish section review after a scored take."""
        # Section reviews are deliberate, bounded practice. Stop at the
        # selected boundary, preserve detailed feedback, and never
        # auto-advance to a different passage.
        self.transport.stop_automatic()
        self.take.finish_section_review()
        self.transport.finish_rewind()
        self.lesson.select_opening(0.0)
        self.notices.feedback = "Section review finished · " + result.summary
        self.notices.next_action = "Review the notes or press Start for the whole passage."

    def finish_partial_recovery(self, result, now: float, *, exposure=None):
        """Complete finish partial recovery after a scored take."""
        # A clean *partial* recovery cannot confer full passage mastery.
        # Clear the bounded review before the scheduled full-pass retry.
        self.take.prepare_full_retry()
        self.lesson.select_opening(exposure.from_beat if exposure is not None else 0.0)
        self.transport_timing.schedule_preparation(self.lesson.opening_beat, now=now,
            from_visual=self.transport.visual_offset_beats + self.transport.play_from_beat
                + self.transport_timing.elapsed_beat(now-self.transport.run_at),
            reverse_seconds=SETTINGS.feedback_seconds)
        self.notices.feedback = "Selected section finished · " + result.summary
        self.notices.next_action = "Next: play the whole passage from its beginning to earn mastery."


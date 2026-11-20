"""Owns the mutable musical timeline and presentation loop state.

PracticeEngine keeps MIDI grading, learning decisions, revision acknowledgements,
and locking. This component owns the forward/reverse score-clock state and the
single empty preparation measure between repeated takes. No engine import.
"""
from __future__ import annotations

from dataclasses import dataclass

from .transport_projection import VisualMotionSnapshot, project_visual_motion
from .notation.practice_timeline import (
    source_preparation_measure, UNLOADED_GAP_BEATS,
)
from .application.musical_scheduler import SCHEDULER, PassagePlan
from .application.transport_commands import resume_timeline, resume_timing


@dataclass
class VisualTransport:
    _pause_floor: float | None = None
    run_at: float = 0.0
    play_from_beat: float = 0.0
    pending_rewind: float | None = None
    paused: bool = False
    paused_at: float = 0.0
    next_at: float = 0.0
    visual_offset_beats: float = 0.0
    _preview_loop_pending: bool = False
    _visual_rewind_from: float | None = None
    _visual_rewind_to: float | None = None
    _visual_rewind_at: float = 0.0
    _visual_rewind_seconds: float = 0.0
    _retry_previous_pass: bool = False
    practice_preparation: dict | None = None
    _preparation_pending: bool = False
    _preparation_at: float = 0.0
    visual_gap_beats: float = UNLOADED_GAP_BEATS
    # The one announced automatic continuation: (source_from_beat, graded
    # run_at, start BPM). Set when the engine schedules the next take of the
    # same stage, published unchanged as score_queue_next while the rest
    # runs, and started with exactly this run_at and BPM. Nothing adds a
    # lead or recomputes the tempo later.
    announced_continuation: PassagePlan | None = None
    # Identity of the announcement (part of score_queue_next.plan_id). A new
    # announcement is new ink; a re-timed one keeps its admitted ink.
    announce_serial: int = 0

    @property
    def preview_loop_pending(self) -> bool:
        return self._preview_loop_pending

    @property
    def retry_previous_pass(self) -> bool:
        return self._retry_previous_pass

    @property
    def preparation_pending(self) -> bool:
        return self._preparation_pending

    @property
    def preparation_deadline(self) -> float:
        """Only VisualTransport owns the pending rest/preparation epoch."""
        return self._preparation_at

    def schedule_preview_repeat(self, *, source_seconds: float,
                                source_bpm: float,presentation_bpm: float,
                                rest_measurement,now: float,
                                reading_horizon_beats: float) -> float:
        """Own the next ungraded preview's rest and its forward deadline.

        An absent MIDI device may repeat source audio/ink but cannot create
        graded presses, settle progress, or choose another musical timeline.
        """
        self.queue_preview_repetition()
        short = SCHEDULER.measured_rest(
            rest_measurement,now=now,bpm=presentation_bpm)
        deadline = short if short is not None else SCHEDULER.missing_horizon(
            deadline=SCHEDULER.repeat(
                run_at=self.run_at,source_seconds=source_seconds,
                gap_beats=self.visual_gap_beats,bpm=source_bpm),
            rest_beats=self.visual_gap_beats,
            reading_horizon_beats=reading_horizon_beats,
            bpm=presentation_bpm)
        self.announce_continuation(0.0,deadline,source_bpm)
        return deadline

    def queue_preview_repetition(self) -> None:
        """A preview may repeat, but no graded attempt is awarded."""
        self._preview_loop_pending = True

    def set_retry_previous_pass(self, enabled: bool) -> None:
        """Track retry lifecycle without bypassing the transport owner."""
        self._retry_previous_pass = bool(enabled)

    def finish_preparation_gate(self) -> None:
        """Release only the pending preparation flag, retaining authored rest."""
        self._preparation_pending = False

    def announce_continuation(self, source_from_beat: float,
                              deadline: float, bpm: float) -> None:
        self.announce_serial += 1
        self.announced_continuation = SCHEDULER.passage(
            from_beat=source_from_beat,deadline=deadline,bpm=bpm)
        self.next_at = float(deadline)

    def retime_announcement(self, deadline: float) -> None:
        """Keep the announced (already admitted) ink; move only its deadline
        to where that ink now reaches the playhead (Resume in a rest)."""
        self.announced_continuation = SCHEDULER.retime_passage(
            self.announced_continuation,deadline=deadline)
        self.next_at = float(deadline)

    def cancel_continuation(self) -> None:
        """Cancel an uncommitted next-take deadline and its announcement."""
        self.next_at = 0.0
        self.announced_continuation = None

    def withdraw_announcement(self) -> None:
        """Retire only the advertised successor, retaining a waiting rest."""
        self.announced_continuation = None

    def clear_pause_for_restart(self) -> None:
        """An explicit Restart abandons the paused epoch without resuming it.

        Normal Resume must instead call resume() to shift the source clock.
        """
        self._pause_floor = None
        self.paused = False
        self.paused_at = 0.0

    def announced_deadline(self, source_from_beat: float) -> float | None:
        """The announced graded deadline of this source opening, if any."""
        announced = self.announced_continuation
        if (announced is None or abs(announced[0] - source_from_beat) > 1e-7
                or not self.next_at or abs(announced[1] - self.next_at) > 1e-9):
            return None
        return announced[1]

    def announced_bpm(self) -> float | None:
        """The announced next take's start BPM while the announcement holds."""
        announced = self.announced_continuation
        if announced is None or self.announced_deadline(announced[0]) is None:
            return None
        return announced[2]

    def reset_for_stop(self, *, rewind_seconds: float) -> None:
        """Forget the visible attempt but retain the loaded score's gap duration."""
        self._pause_floor = None
        self.paused = False
        self.paused_at = 0.0
        self.visual_offset_beats = 0.0
        self._preview_loop_pending = False
        self._visual_rewind_from = None
        self._visual_rewind_to = None
        self._visual_rewind_at = 0.0
        self._visual_rewind_seconds = rewind_seconds
        self._retry_previous_pass = False
        self.practice_preparation = None
        self._preparation_pending = False
        self._preparation_at = 0.0
        self.next_at = 0.0
        self.announced_continuation = None
        self.pending_rewind = None
        self.play_from_beat = 0.0

    def begin_take(self, *, loop_continuation: bool) -> None:
        """Clear the former attempt while retaining its finished preparation."""
        self._pause_floor = None
        self.paused = False
        self.paused_at = 0.0
        self._preview_loop_pending = False
        self._visual_rewind_from = None
        self._visual_rewind_to = None
        self._retry_previous_pass = False
        self._preparation_pending = False
        if loop_continuation and self.practice_preparation is not None:
            self.practice_preparation["phase"] = "complete"
        else:
            self.practice_preparation = None
        self.next_at = 0.0
        self.announced_continuation = None
        self.pending_rewind = None

    def schedule_source_preparation(
        self, source_model: dict, *, source_from_beat: float,
        from_visual: float, now: float, reverse_seconds: float,
        bpm: float, horizon_beats: float = 0.0,
        short_deadline: float | None = None, announce: bool = True,
        reading_lead_included: bool = True,
    ) -> float:
        """Derive the single written rest from the source's meter and staves.

        Source-space placement, reverse animation and the absolute deadline
        share this transport owner. No engine or second clock is involved.
        """
        measure = source_preparation_measure(
            source_model,source_from_beat,0.0)
        return self.schedule_preparation(
            measure, source_from_beat=source_from_beat,
            from_visual=from_visual, now=now,
            reverse_seconds=reverse_seconds, bpm=bpm,
            horizon_beats=horizon_beats,short_deadline=short_deadline,
            announce=announce,reading_lead_included=reading_lead_included)

    def schedule_preparation(
        self, measure: dict, *, source_from_beat: float,
        from_visual: float, now: float, reverse_seconds: float, bpm: float,
        horizon_beats: float = 0.0,
        short_deadline: float | None = None, announce: bool = True,
        reading_lead_included: bool = True,
    ) -> float:
        """Reverse in-place, then traverse one authentic empty measure."""
        measure["end_beat"] = self.visual_offset_beats + source_from_beat
        measure["start_beat"] = measure["end_beat"] - measure["duration_beats"]
        self.practice_preparation = {
            "pass_start_beat": self.visual_offset_beats,
            "source_from_beat": source_from_beat,
            "measure": measure, "phase": "reverse",
        }
        self._preparation_pending = True
        self.pending_rewind = source_from_beat
        self._visual_rewind_from = from_visual
        self._visual_rewind_to = measure["start_beat"]
        plan = SCHEDULER.prepare(
            now=now,reverse_seconds=reverse_seconds,
            rest_beats=measure["duration_beats"],
            horizon_beats=horizon_beats,bpm=bpm,
            include_reading=reading_lead_included or not announce,
            short_deadline=short_deadline,announce=announce)
        self._visual_rewind_at = plan.reverse_at
        self._visual_rewind_seconds = plan.reverse_seconds
        self._preparation_at = plan.prepare_at
        self.next_at = plan.run_at
        self._preview_loop_pending = False
        return self.next_at

    def cancel_preparation(self) -> None:
        """End a failed warm-up's automatic retry without erasing the score."""
        self._preparation_pending = False
        self.practice_preparation = None
        self.pending_rewind = None
        self.announced_continuation = None
        self._visual_rewind_from = None
        self._visual_rewind_to = None

    def preparation_schedule(self) -> dict | None:
        """Absolute monotonic endpoints for the same rewind/preparation clock.

        Python MIDI transitions and Godot's rendering use these deadlines.
        Poll latency must never become another animation origin.
        """
        if not self._preparation_pending or self._visual_rewind_from is None:
            return None
        return {
            "reverse_at_ms": self._visual_rewind_at * 1000.0,
            "prepare_at_ms": self._preparation_at * 1000.0,
            "deadline_at_ms": self.next_at * 1000.0,
            "from_beat": self._visual_rewind_from,
            "to_beat": self._visual_rewind_to,
        }

    def clear_grading_floor(self) -> None:
        self._pause_floor = None

    def musical_seconds(self, at: float, *, grading_after: float) -> float:
        """Source time freezes for a held key through Pause and reading lead."""
        seconds = at-self.run_at
        if self._pause_floor is None:
            return seconds
        if self.paused:
            return min(seconds,self._pause_floor)
        if at < grading_after:
            return max(seconds,self._pause_floor)
        return seconds

    def grading_is_frozen(self, at: float, *, grading_after: float) -> bool:
        return self._pause_floor is not None and at < grading_after

    def pause(self, *, at: float, freeze_grading: bool = False,
              grading_after: float = 0.0) -> None:
        """Freeze the presentation clock at one sampled instant."""
        if self.paused:
            raise ValueError("Transport is already paused")
        if freeze_grading:
            self._pause_floor = self.musical_seconds(at,grading_after=grading_after)
        self.paused_at = at
        self.paused = True

    def resume(self, *, now: float, shift_run_at: bool) -> None:
        """Advance active deadlines by the exact elapsed paused duration.

        An inactive clock's zero sentinel must stay zero. The source beat and
        continuous visual offset never change during pause/resume.
        """
        if not self.paused:
            raise ValueError("Transport is not paused")
        duration = now - self.paused_at
        self.run_at = SCHEDULER.shift_epoch(self.run_at,duration,active=shift_run_at)
        self.next_at = SCHEDULER.shift_epoch(
            self.next_at,duration,active=bool(self.next_at))
        if self.announced_continuation is not None:
            self.announced_continuation = SCHEDULER.shift_passage(
                self.announced_continuation,seconds=duration)
        self._visual_rewind_at = SCHEDULER.shift_epoch(
            self._visual_rewind_at,duration,
            active=self._visual_rewind_from is not None)
        self._preparation_at = SCHEDULER.shift_epoch(
            self._preparation_at,duration,active=self._preparation_pending)
        self.paused_at = 0.0
        self.paused = False

    def resume_attempt(self, *, now: float, learning: bool, running: bool,
                       automatic_feedback: bool, grading_after: float, mode: str,
                       pause_context: str | None, bpm: float | None,
                       count_in_beats: float, full_count_in_beats: float, bar_beats: float,
                       reading_lead_seconds: float, reuse_pending_score: bool,
                       midi_connected: bool, preview: bool,
                       scheduled_deadline: float | None):
        """Validate, shift and authorize the resumed source clock once."""
        shift = resume_timeline(
            paused=self.paused,learning=learning,running=running,
            preview_pending=self.preview_loop_pending,
            automatic_feedback=automatic_feedback)
        paused_at, previous_origin = self.paused_at,self.run_at
        if reuse_pending_score and (
                reading_lead_seconds <= 0.0 or not (shift and running
                and mode in ("practice", "perform"))
                or pause_context != "count_in" or self.run_at <= paused_at):
            raise ValueError("Cannot reuse a passage after graded notes began")
        frozen = self._pause_floor
        had_reading_lead = grading_after > paused_at
        self.resume(now=now,shift_run_at=shift)
        if had_reading_lead:
            grading_after += max(0.0,now-paused_at)
        timing = resume_timing(
            now=now,origin=self.run_at,previous_origin=previous_origin,
            paused_at=paused_at,frozen_seconds=frozen,
            grading_after=grading_after,had_reading_lead=had_reading_lead,
            shift_run_at=shift,running=running,mode=mode,
            pause_context=pause_context,bpm=bpm,count_in_beats=count_in_beats,
            full_count_in_beats=full_count_in_beats,
            bar_beats=bar_beats,reading_lead_seconds=reading_lead_seconds,
            reuse_pending_score=reuse_pending_score,
            midi_connected=midi_connected,preview=preview,
            scheduled_deadline=scheduled_deadline)
        self.run_at = timing.origin
        return previous_origin,shift,timing

    def position(
        self, now: float, *, phrase_length: float, bpm: float,
        running: bool, pending_auto_result: bool,
        tempo_map=None,
    ) -> tuple[float, float, float]:
        measure = (self.practice_preparation["measure"]
                   if self.practice_preparation is not None else None)
        return project_visual_motion(VisualMotionSnapshot(
            phrase_length=phrase_length,
            visual_offset=self.visual_offset_beats,
            play_from_beat=self.play_from_beat,
            bpm=bpm,
            run_at=self.run_at,
            running=running,
            preparation_pending=self._preparation_pending,
            preparation_at=self._preparation_at,
            preparation_measure=measure,
            rewind_from=self._visual_rewind_from,
            rewind_to=self._visual_rewind_to,
            rewind_at=self._visual_rewind_at,
            rewind_seconds=self._visual_rewind_seconds,
            pending_auto_result=pending_auto_result,
            preview_loop_pending=self._preview_loop_pending,
            gap_beats=self.visual_gap_beats,
            paused=self.paused,
        ), now, tempo_map=tempo_map)

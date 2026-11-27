"""Owns the mutable musical timeline and presentation loop state.

Assessment, lesson selection and command execution retain their distinct
owners. This transport owns forward/reverse score-clock state and the empty
preparation measure between repeated takes. No facade backreference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from .source_timing import UNLOADED_GAP_BEATS
from .application.musical_scheduler import SCHEDULER
from .application.transport_commands import resume_timeline, resume_timing
from .application.musical_timeline import MusicalTimeline


@dataclass
class VisualTransport:
    def select_opening(self, from_beat: float) -> None:
        self.play_from_beat = from_beat

    def prepare_rewind(self, from_beat: float) -> None:
        self.pending_rewind = from_beat

    def finish_rewind(self) -> None:
        self.pending_rewind = None

    def install_timed_origin(self, *, from_beat: float, run_at: float,
                             gap_beats: float) -> None:
        """Install the already selected onset shared by score and grading."""
        self.play_from_beat = from_beat
        self.run_at = run_at
        self.visual_gap_beats = gap_beats

    _pause_floor: float | None = None
    run_at: float = 0.0
    play_from_beat: float = 0.0
    pending_rewind: float | None = None
    # The same musical timeline owns running and paused. PlaybackSession's
    # public running property delegates here; no separate active flag.
    running: bool = False
    paused: bool = False
    paused_at: float = 0.0
    # One transport identity and metrical count-in alongside the clock
    # which the immutable score and MIDI grading actually consume.
    transport_id: int = 0
    count_in_beats: float = 0.0
    count_in_bar_beats: float = 4.0
    count_in_meter: list[int] = field(default_factory=lambda: [4, 4])
    # A take has settled and the next exposure follows it.
    continuation_pending: bool = False
    visual_gap_beats: float = UNLOADED_GAP_BEATS
    # Identity of the selected continuation. A new announcement is new ink;
    # a re-timed one keeps its admitted ink.
    # Presentation schedule facts live with the one forward visual transport.
    next_boundary_beat: float = 0.0
    # The declared musical timeline: every timed take is placed on it and
    # Godot draws and counts in from it.
    musical: MusicalTimeline = field(default_factory=MusicalTimeline)
    # Beats of printed ink Godot last reported ahead of its playhead; a new
    # run starts its count-in after it.
    ink_ahead_beats: float = 0.0
    # Beats a Free target needs to travel in from off the right edge of the
    # staff (plus the clef header) to the playhead, as Godot measured it.
    free_travel_beats: float = 0.0

    def report_free_travel(self, beats) -> None:
        value = float(beats)
        if not math.isfinite(value) or not 0.0 <= value <= 256.0:
            raise ValueError("Invalid Free travel measurement")
        self.free_travel_beats = value

    def report_ink_ahead(self, beats) -> None:
        value = float(beats)
        if not math.isfinite(value) or not 0.0 <= value <= 256.0:
            raise ValueError("Invalid ink-ahead measurement")
        self.ink_ahead_beats = value

    def advance_boundary(self, beat: float) -> None:
        """Install the next source checkpoint chosen by AttemptProgression."""
        self.next_boundary_beat = beat

    def reset_for_stop(self, *, preserve_musical: bool = False,
                       now: float | None = None) -> None:
        """Reset grading; internal handoffs may retain the moving rest."""
        self.running = False
        self._pause_floor = None
        self.paused = False
        self.paused_at = 0.0
        self.continuation_pending = False
        self.pending_rewind = None
        self.play_from_beat = 0.0
        if preserve_musical and now is not None and self.musical.open:
            self.musical.bridge_to_rest(now)
        else:
            self.musical.reset()

    def begin_take(self) -> None:
        """Clear the former attempt."""
        self._pause_floor = None
        self.paused = False
        self.paused_at = 0.0
        self.continuation_pending = False
        self.pending_rewind = None

    def clear_grading_floor(self) -> None:
        self._pause_floor = None

    def musical_seconds(self, at: float, *, grading_after: float) -> float:
        """Source time freezes for a held key through Pause and reading lead."""
        seconds = at-self.run_at
        if self._pause_floor is None:
            return seconds
        if self.paused:
            # A second Pause inside Resume's reading lead retains the
            # already frozen source position. Raw at-run_at is deliberately
            # behind that position until this lead ends. Outside that case,
            # retain earlier corrected hardware timestamps before Pause.
            if self.paused_at < grading_after:
                return self._pause_floor
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
        self.musical.pause(at)

    def resume(self, *, now: float, shift_run_at: bool) -> None:
        """Advance active deadlines by the exact elapsed paused duration.

        An inactive clock's zero sentinel must stay zero. The source beat and
        continuous visual offset never change during pause/resume.
        """
        if not self.paused:
            raise ValueError("Transport is not paused")
        duration = now - self.paused_at
        self.run_at = SCHEDULER.shift_epoch(self.run_at,duration,active=shift_run_at)
        self.paused_at = 0.0
        self.paused = False
        self.musical.resume(now)

    def resume_attempt(self, *, now: float, learning: bool, running: bool,
                       automatic_feedback: bool, grading_after: float, mode: str,
                       pause_context: str | None, bpm: float | None,
                       count_in_beats: float, full_count_in_beats: float, bar_beats: float,
                       reading_lead_seconds: float,
                       midi_connected: bool,
                       scheduled_deadline: float | None):
        """Validate, shift and authorize the resumed source clock once."""
        shift = resume_timeline(
            paused=self.paused,learning=learning,running=running,
            automatic_feedback=automatic_feedback)
        paused_at, previous_origin = self.paused_at,self.run_at
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
            midi_connected=midi_connected,
            scheduled_deadline=scheduled_deadline)
        self.run_at = timing.origin
        return previous_origin,shift,timing


    def await_continuation(self) -> None:
        """A settled take's next exposure follows it."""
        self.continuation_pending = True

    def cancel_continuation(self) -> None:
        """Nothing follows the settled take."""
        self.continuation_pending = False

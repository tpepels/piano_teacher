"""Owns the mutable musical timeline and presentation loop state.

PracticeEngine keeps MIDI grading, learning decisions, revision acknowledgements,
and locking. This component owns the forward/reverse score-clock state and the
single empty preparation measure between repeated takes. No engine import.
"""
from __future__ import annotations

from dataclasses import dataclass

from .transport_projection import VisualMotionSnapshot, project_visual_motion


@dataclass
class VisualTransport:
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
    visual_gap_beats: float = 4.0

    def reset_for_stop(self, *, rewind_seconds: float) -> None:
        """Forget the visible attempt but retain the loaded score's gap duration."""
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
        self.pending_rewind = None
        self.play_from_beat = 0.0

    def begin_take(self, *, loop_continuation: bool) -> None:
        """Clear the former attempt while retaining its finished preparation."""
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
        self.pending_rewind = None

    def schedule_preparation(
        self, measure: dict, *, source_from_beat: float,
        from_visual: float, now: float, reverse_seconds: float, bpm: float,
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
        self._visual_rewind_at = now
        self._visual_rewind_seconds = max(.05, reverse_seconds)
        self._preparation_at = now + self._visual_rewind_seconds
        self.next_at = self._preparation_at + measure["duration_beats"] * 60 / bpm
        self._preview_loop_pending = False
        return self.next_at

    def pause(self, *, at: float) -> None:
        """Freeze the presentation clock at one sampled instant."""
        if self.paused:
            raise ValueError("Transport is already paused")
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
        if shift_run_at:
            self.run_at += duration
        if self.next_at:
            self.next_at += duration
        if self._visual_rewind_from is not None:
            self._visual_rewind_at += duration
        if self._preparation_pending:
            self._preparation_at += duration
        self.paused_at = 0.0
        self.paused = False

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


class TransportField:
    """Compatibility alias while engine callers move to VisualTransport.

    Existing tests, HTTP handlers, and integrations can still inspect or
    assign engine.run_at, engine.pending_rewind, etc. No duplicated storage.
    """

    def __init__(self, name: str):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return getattr(instance.visual_transport, self.name)

    def __set__(self, instance, value) -> None:
        setattr(instance.visual_transport, self.name, value)

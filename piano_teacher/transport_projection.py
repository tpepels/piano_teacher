"""Pure quarter-beat transport projection.

The engine owns clocks, pause/resume, MIDI grading and transitions. This
module only projects a captured transport state onto the continuous score.
No application imports, mutation, current-time reads or rendering calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .exercise_contracts import TempoMap


@dataclass(frozen=True)
class VisualMotionSnapshot:
    phrase_length: float
    visual_offset: float
    play_from_beat: float
    bpm: float
    run_at: float
    running: bool
    preparation_pending: bool
    preparation_at: float
    preparation_measure: Mapping | None
    rewind_from: float | None
    rewind_to: float | None
    rewind_at: float
    rewind_seconds: float
    pending_auto_result: bool
    preview_loop_pending: bool
    gap_beats: float
    paused: bool


def project_visual_motion(
    state: VisualMotionSnapshot, now: float, *, tempo_map: TempoMap | None = None,
) -> tuple[float, float, float]:
    """Return (absolute visible beat, signed beats/second, next target beat).

    The caller supplies paused_at instead of wall-clock time while paused.
    Rewind intentionally uses its own phase velocity, not the practice BPM.
    """
    length = state.phrase_length
    forward_gap = ((state.pending_auto_result or state.preview_loop_pending)
                   and state.rewind_from is None and not state.preparation_pending)
    if tempo_map is not None and now >= state.run_at and (state.running or forward_gap):
        if abs(tempo_map.duration_beats-length) > 1e-7:
            raise ValueError("Visual source duration differs from grading tempo map")
        source_time = tempo_map.seconds_at(state.play_from_beat)
        end_time = tempo_map.seconds_at(length)-source_time
        elapsed = now-state.run_at
        if elapsed < end_time:
            beat = tempo_map.beat_at(source_time+elapsed)
            speed = tempo_map.bpm_at(beat)/60.0
        else:
            beat = length+(elapsed-end_time)*state.bpm/60.0
            speed = state.bpm/60.0
        return (state.visual_offset+beat, 0.0 if state.paused else speed,
                state.visual_offset+length+(state.gap_beats if forward_gap else 0.0))

    position = state.visual_offset + state.play_from_beat
    speed = 0.0
    target = state.visual_offset + length

    if state.running:
        position += (now-state.run_at)*state.bpm/60
        speed = state.bpm/60
    elif state.preparation_pending and now >= state.preparation_at:
        if state.preparation_measure is None:
            raise ValueError("Active preparation must have a measure")
        measure = state.preparation_measure
        target = measure["end_beat"]
        position = min(target, measure["start_beat"]
                       + (now-state.preparation_at)*state.bpm/60)
        speed = state.bpm/60 if position < target else 0.0
    elif state.rewind_from is not None:
        if state.rewind_to is None:
            raise ValueError("Active rewind must have a target")
        target = state.rewind_to
        seconds = max(.05, state.rewind_seconds)
        progress = min(1.0, max(0.0, (now-state.rewind_at)/seconds))
        position = state.rewind_from + (target-state.rewind_from)*progress
        speed = (target-state.rewind_from)/seconds if progress < 1 else 0.0
    elif state.pending_auto_result or state.preview_loop_pending:
        target += state.gap_beats
        # The end of the rest is a scheduled handoff, not an instruction to
        # stop the musical clock. The engine may process that handoff a frame
        # or a state query later. Keep the one continuous visual axis moving
        # until a different transport phase is actually published.
        position = state.visual_offset + max(
            length, state.play_from_beat + (now-state.run_at)*state.bpm/60)
        speed = state.bpm/60
    return position, 0.0 if state.paused else speed, target

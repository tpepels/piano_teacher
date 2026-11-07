"""Construct a backend state snapshot under the caller's existing session lock.

The builder owns presentation data assembly and preserves the monotonic
sampling order, while PracticeEngine retains MIDI, lesson, grading, and
musical transition authority. The returned dataclass is projected separately.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from ..state_projection import (
    ActivitySnapshot, GuidedSnapshot, SessionSnapshot, TimingSnapshot,
)
from .lesson_snapshot import build_lesson_snapshot
from ..learner_state import placement_candidate


@dataclass(frozen=True)
class SnapshotValues:
    """Only the captured fields consumed by the presentation projection.

    This is shallow immutable: its collaborators remain owned by the session,
    whose existing lock protects the entire capture.
    """
    _guided_recovery_pending: bool
    _guided_return: tuple[str, float] | None
    _remediation_active: Any
    auto: bool
    awaiting_score_revision: int | None
    count_in_bar_beats: float
    count_in_beats: float
    count_in_meter: list[int]
    feedback: str
    feedback_marks: list[dict]
    feedback_unmapped: int
    fingerprint: str
    guided_range: tuple[float, float] | None
    is_builtin_warmup: bool
    metronome: bool
    midi_input_count: int
    midi_input_note: int | None
    midi_input_at: float | None
    midi_connected: bool
    midi_device: str
    midi_notes: int
    teaching_active: bool
    mode: str
    next_action: str
    next_at: float
    open_from_beat: float
    pause_context: str | None
    paused: bool
    paused_at: float
    pending_result: Any
    pending_rewind: float | None
    performance_summary: Any
    persistent_hints: bool
    plan: Any
    play_from_beat: float
    practice_preparation: Any
    preview_only: bool
    recovery_notice: Any
    retry_range: Any
    review_end_beat: float | None
    run_at: float
    running: bool
    score_revision: int
    transport_id: int
    visual_offset_beats: float


@dataclass(frozen=True)
class SnapshotReadPorts:
    """Named operations, sampled under the engine lock.

    The sole write port synchronizes the preparation gap after source lookup.
    """
    seek_grid: Callable[..., Any]
    learner_snapshot: Callable[..., Any]
    elapsed_beat: Callable[..., Any]
    phase: Callable[..., Any]
    source_model: Callable[..., Any]
    live_feedback: Callable[..., Any]
    visual_motion: Callable[..., Any]
    active_tempo_map: Callable[..., Any]
    display_phrase: Callable[..., Any]
    guided_marks: Callable[..., Any]
    listen_snapshot: Callable[..., Any]
    live_input_snapshot: Callable[..., Any]
    preparation_schedule: Callable[..., Any]
    teaching_snapshot: Callable[..., Any] | None
    set_visual_gap_beats: Callable[[float], None]
    clock: Callable[[], float]


def capture(state: SnapshotValues, reads: SnapshotReadPorts) -> SessionSnapshot:
    """Capture values under the session lock, including stateful read adapters.

    The clock is sampled ONCE: every time-derived field of one snapshot
    describes the same instant. Teaching snapshots may tick the controller;
    all such work finishes before pure projection.
    """
    sampled_at = reads.clock()
    p = state.plan
    seek_grid = reads.seek_grid()
    activity = ActivitySnapshot(
        sampled_at=sampled_at,
        learner=reads.learner_snapshot() if p is not None else None,
        placement_available=(not state.is_builtin_warmup and placement_candidate(p) is not None) if p is not None else False,
        skip_available=(not state.is_builtin_warmup and p.lesson_step_number < len(p.lesson_steps)) if p is not None else False,
        seek_available=state.paused and seek_grid is not None,
        seek_range=({"first_bar": p.active_phrase.first_bar, "last_bar": p.active_phrase.last_bar}
                    if seek_grid is not None else None),
        next_action=state.next_action,
        transition_now=((state.paused_at if state.paused else sampled_at)
            if state.next_at and (state.pending_result is not None or state.pending_rewind is not None) else 0.0),
        next_at=state.next_at,
        pending_transition=state.pending_result is not None or state.pending_rewind is not None,
        retry_range=state.retry_range,
        notice_now=sampled_at if state.recovery_notice is not None else 0.0,
        recovery_notice=state.recovery_notice,
        guided_recovery=state._guided_recovery_pending or state._guided_return is not None,
        pause_context=state.pause_context,
        demo=reads.listen_snapshot(),
        performance_summary=state.performance_summary,
        review_pending=state.review_end_beat is not None,
        midi_input_count=state.midi_input_count,
        midi_input_note=state.midi_input_note,
        midi_now=sampled_at if state.midi_input_at is not None else 0.0,
        midi_input_at=state.midi_input_at,
        metronome=state.metronome,
        hints_enabled=state.persistent_hints,
        fingering=p.piece.fingering_plan.summary()
            if p is not None and p.piece.fingering_plan is not None else None,
    )
    visual_now = state.paused_at if state.paused else sampled_at
    visual_beat = state.play_from_beat
    if state.running and visual_now >= state.run_at and p is not None:
        visual_beat += reads.elapsed_beat(visual_now-state.run_at)
    activity = replace(activity, midi_display=reads.live_input_snapshot(
        now=sampled_at,
        phrase=p.active_phrase if p is not None else None,
        hand=p.hand if p is not None else "both", beat=visual_beat,
        playing=(p is not None and state.mode in ("practice", "perform")
                 and (state.running or reads.phase(visual_now) == "ready")),
    ))
    if p is None:
        return SessionSnapshot(mode=state.mode, feedback=state.feedback,
            device=state.midi_device, revision=state.score_revision,
            transport_id=state.transport_id, activity=activity)
    practice_timeline = reads.source_model()["practice_timeline"]
    gap_beats = practice_timeline["gap"]["duration_beats"]
    reads.set_visual_gap_beats(gap_beats)
    ex, variant = p.exercise, p.active_variant
    # Only the current exercise's hand rows are used by the HUD.
    # Capturing/freezing the full sequence of thousands of lesson stages
    # every 20 ms makes a large source freeze the in-process control queue.
    # Keep the total as one count; retain the complete source course in
    # LearningPlan for Lesson Path navigation and mastery.
    all_steps = p.lesson_steps
    lesson_steps = tuple(
        (step.exercise_index, step.hand, step.key)
        for step in all_steps if step.exercise_index == p.index)
    now = state.paused_at if state.paused else sampled_at
    elapsed = now-state.run_at
    phase = reads.phase(now)
    live_marks = reads.live_feedback(elapsed) if phase == "playing" else []
    visual_motion = reads.visual_motion(now)
    lesson = build_lesson_snapshot(
        p, ex, variant, fingerprint=state.fingerprint,
        warmup=state.is_builtin_warmup, lesson_steps=lesson_steps,
        lesson_step_count=len(all_steps))
    tempo_map = reads.active_tempo_map()
    # Local-zero source timing followed by the explicit practice-BPM
    # silence. These exact segments are sent to Godot and retained
    # through the automatic-rest phase with the same run_at timestamp.
    visual_segments = ()
    tempo_segments = ()
    if tempo_map is not None:
        local_map = tempo_map.from_beat(state.play_from_beat)
        tempo_segments = local_map.as_segments()
        visual_segments = (*tempo_segments, {
            "start_beat": local_map.duration_beats,
            "end_beat": local_map.duration_beats+gap_beats,
            "bpm": float(p.bpm),
            "start_seconds": local_map.duration_seconds,
        })
    timing = TimingSnapshot(
        sampled_at=sampled_at, now=now, run_at=state.run_at,
        tempo_segments=tempo_segments,
        visual_tempo_segments=visual_segments,
        visual_preparation_schedule=reads.preparation_schedule(),
        mapped_clock_beat=(reads.elapsed_beat(now-state.run_at)
                           if tempo_map is not None else None),
        running=state.running, paused=state.paused, auto=state.auto,
        preview_only=state.preview_only, play_from_beat=state.play_from_beat,
        open_from_beat=state.open_from_beat, pending_rewind=state.pending_rewind,
        review_end_beat=state.review_end_beat,
        awaiting_score_revision=state.awaiting_score_revision,
        count_in_beats=state.count_in_beats,
        count_in_bar_beats=state.count_in_bar_beats, count_in_meter=state.count_in_meter,
        midi_notes=state.midi_notes,
        visual_offset_beats=state.visual_offset_beats,
        visual_gap_beats=gap_beats, visual_motion=visual_motion,
        practice_timeline=practice_timeline, practice_preparation=state.practice_preparation,
        take_result=({"clean": bool(state.pending_result.clean),
                      "accepted": bool(state.pending_result.passed),
                      "correct": state.pending_result.correct,
                      "total": len(state.pending_result.notes)}
                     if state.mode == "practice" and state.pending_result is not None else None),
        feedback_marks=state.feedback_marks, live_marks=live_marks,
        feedback_unmapped=state.feedback_unmapped,
        scoring_available=(not state.preview_only and state.midi_connected
                           and state.mode in ("practice", "perform")),
    )
    guided = None
    if state.mode == "learn" and state.teaching_active:
        teaching = reads.teaching_snapshot(now=sampled_at)
        phrase = reads.display_phrase()
        guided = GuidedSnapshot(
            teaching=teaching,
            fragment={"first_bar": phrase.first_bar, "last_bar": phrase.last_bar,
                      "start_beat": state.guided_range[0], "end_beat": state.guided_range[1]},
            phase=reads.phase(now),
            has_more_units=activity.learner["next_unit"] is not None and state._guided_return is None,
            returning=bool(state._guided_return),
            required_notes=(len(state._remediation_active.variant.notes)
                            if state._remediation_active is not None
                            else len(phrase.notes)),
            duration_beats=phrase.end-phrase.start,
            feedback_marks=reads.guided_marks(teaching),
        )
    return SessionSnapshot(mode=state.mode, feedback=state.feedback,
        device=state.midi_device, revision=state.score_revision,
        transport_id=state.transport_id, phase=phase, activity=activity,
        lesson=lesson, timing=timing, guided=guided)


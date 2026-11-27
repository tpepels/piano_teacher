"""Construct a backend state snapshot under the caller's existing session lock.

The builder assembles presentation data from the domain owners and preserves
the monotonic sampling order. The returned dataclass is projected separately;
source lookup cannot mutate musical scheduling state.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from ..state_projection import (
    ActivitySnapshot, GuidedSnapshot, SessionSnapshot, TimingSnapshot,
)
from .lesson_snapshot import build_lesson_snapshot


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
    guided_open_at: float | None
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
    continuation_pending: bool
    open_from_beat: float
    pause_context: str | None
    paused: bool
    paused_at: float
    pending_result: Any
    assessment_verdict: Any
    pending_rewind: float | None
    performance_summary: Any
    persistent_hints: bool
    plan: Any
    play_from_beat: float
    recovery_notice: Any
    retry_range: Any
    run_at: float
    running: bool
    score_revision: int
    transport_id: int


@dataclass(frozen=True)
class SnapshotReadPorts:
    """Named read operations, sampled under the engine lock."""
    learner_snapshot: Callable[..., Any]
    elapsed_beat: Callable[..., Any]
    phase: Callable[..., Any]
    practice_timing: Callable[..., Any]
    live_feedback: Callable[..., Any]
    active_tempo_map: Callable[..., Any]
    display_phrase: Callable[..., Any]
    guided_marks: Callable[..., Any]
    listen_snapshot: Callable[..., Any]
    live_input_snapshot: Callable[..., Any]
    teaching_snapshot: Callable[..., Any] | None
    clock: Callable[[], float]


def capture(state: SnapshotValues, reads: SnapshotReadPorts) -> SessionSnapshot:
    """Capture values under the session lock, using read-only adapters.

    The clock is sampled ONCE: every time-derived field of one snapshot
    describes the same instant. Teaching/transport advancement belongs to the worker and command boundary;
    reading these adapters cannot advance an exposure.
    """
    sampled_at = reads.clock()
    p = state.plan
    activity = ActivitySnapshot(
        sampled_at=sampled_at,
        learner=reads.learner_snapshot() if p is not None else None,
        next_action=state.next_action,
        transition_pending=(state.continuation_pending
            and (state.pending_result is not None or state.pending_rewind is not None)),
        retry_range=state.retry_range,
        notice_now=sampled_at if state.recovery_notice is not None else 0.0,
        recovery_notice=state.recovery_notice,
        guided_recovery=state._guided_recovery_pending or state._guided_return is not None,
        pause_context=state.pause_context,
        demo=reads.listen_snapshot(),
        performance_summary=state.performance_summary,
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
    practice_timeline = reads.practice_timing()
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
    lesson = build_lesson_snapshot(
        p, ex, variant, fingerprint=state.fingerprint,
        lesson_steps=lesson_steps,
        lesson_step_count=len(all_steps))
    tempo_map = reads.active_tempo_map()
    # Local-zero source timing of the selected window (Listen audio and
    # the published duration read it).
    tempo_segments = ()
    if tempo_map is not None:
        tempo_segments = tempo_map.from_beat(state.play_from_beat).as_segments()
    timing = TimingSnapshot(
        sampled_at=sampled_at, now=now, run_at=state.run_at,
        tempo_segments=tempo_segments,
        mapped_clock_beat=(reads.elapsed_beat(now-state.run_at)
                           if tempo_map is not None else None),
        running=state.running, paused=state.paused, auto=state.auto,
        play_from_beat=state.play_from_beat,
        open_from_beat=state.open_from_beat, pending_rewind=state.pending_rewind,
        awaiting_score_revision=state.awaiting_score_revision,
        count_in_beats=state.count_in_beats,
        count_in_bar_beats=state.count_in_bar_beats, count_in_meter=state.count_in_meter,
        midi_notes=state.midi_notes,
        practice_timeline=practice_timeline,
        take_result=({"clean": bool(state.assessment_verdict.clean)
                            if state.assessment_verdict is not None else False,
                      "accepted": bool(state.assessment_verdict.accepted)
                            if state.assessment_verdict is not None else False,
                      "acceptance_policy": (state.assessment_verdict.policy
                            if state.assessment_verdict is not None else "pending"),
                      "correct": state.pending_result.correct,
                      "total": len(state.pending_result.notes)}
                     if state.mode == "practice" and state.pending_result is not None else None),
        feedback_marks=state.feedback_marks, live_marks=live_marks,
        feedback_unmapped=state.feedback_unmapped,
        scoring_available=(state.midi_connected
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
            arriving=(state.guided_open_at is not None
                      and sampled_at < state.guided_open_at),
        )
    return SessionSnapshot(mode=state.mode, feedback=state.feedback,
        device=state.midi_device, revision=state.score_revision,
        transport_id=state.transport_id, phase=phase, activity=activity,
        lesson=lesson, timing=timing, guided=guided)


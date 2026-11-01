"""Construct a backend state snapshot under the caller's existing session lock.

The builder owns presentation data assembly and preserves the monotonic
sampling order, while PracticeEngine retains MIDI, lesson, grading, and
musical transition authority. The returned dataclass is projected separately.
"""
from __future__ import annotations

from dataclasses import replace
import time

from ..state_projection import (
    ActivitySnapshot, GuidedSnapshot, SessionSnapshot, TimingSnapshot,
)
from .lesson_snapshot import build_lesson_snapshot
from ..learner_state import placement_candidate


def capture(engine) -> SessionSnapshot:
    """Capture values under the session lock, including stateful read adapters.

    Clock reads retain their original order and purpose. Teaching snapshots
    may tick the controller; all such work finishes before pure projection.
    """
    p = engine.plan
    seek_grid = engine._seek_grid()
    activity = ActivitySnapshot(
        sampled_at=time.monotonic(),
        learner=engine._learner_snapshot() if p is not None else None,
        placement_available=(not engine.is_builtin_warmup and placement_candidate(p) is not None) if p is not None else False,
        skip_available=(not engine.is_builtin_warmup and p.lesson_step_number < len(p.lesson_steps)) if p is not None else False,
        seek_available=engine.paused and seek_grid is not None,
        seek_range=({"first_bar": p.active_phrase.first_bar, "last_bar": p.active_phrase.last_bar}
                    if seek_grid is not None else None),
        next_action=engine.next_action,
        transition_now=((engine.paused_at if engine.paused else time.monotonic())
            if engine.next_at and (engine.pending_result is not None or engine.pending_rewind is not None) else 0.0),
        next_at=engine.next_at,
        pending_transition=engine.pending_result is not None or engine.pending_rewind is not None,
        retry_range=engine.retry_range,
        notice_now=time.monotonic() if engine.recovery_notice is not None else 0.0,
        recovery_notice=engine.recovery_notice,
        guided_recovery=engine._guided_recovery_pending or engine._guided_return is not None,
        pause_context=engine.pause_context,
        demo=engine.listen.snapshot(),
        performance_summary=engine.performance_summary,
        review_pending=engine.review_end_beat is not None,
        midi_input_count=engine.midi.input_count,
        midi_input_note=engine.midi.input_note,
        midi_now=time.monotonic() if engine.midi.input_at is not None else 0.0,
        midi_input_at=engine.midi.input_at,
        metronome=engine.library.settings["metronome"],
        hints_enabled=engine.persistent_hints,
        fingering=p.piece.fingering_plan.summary()
            if p is not None and p.piece.fingering_plan is not None else None,
    )
    visual_now = engine.paused_at if engine.paused else time.monotonic()
    visual_beat = engine.play_from_beat
    if engine.running and visual_now >= engine.run_at and p is not None:
        visual_beat += engine._elapsed_beat(visual_now-engine.run_at)
    activity = replace(activity, midi_display=engine.live_input.snapshot(
        now=time.monotonic(),
        phrase=p.active_phrase if p is not None else None,
        hand=p.hand if p is not None else "both", beat=visual_beat,
        playing=(p is not None and engine.mode in ("practice", "perform")
                 and (engine.running or engine._phase(visual_now) == "ready")),
    ))
    if p is None:
        return SessionSnapshot(mode=engine.mode, feedback=engine.feedback,
            device=engine.midi.device, revision=engine.score_revision,
            transport_id=engine.transport_id, activity=activity)
    practice_timeline = engine._source_model()["practice_timeline"]
    engine.visual_gap_beats = practice_timeline["gap"]["duration_beats"]
    ex, variant = p.exercise, p.active_variant
    lesson_steps = tuple((step.exercise_index, step.hand, step.key) for step in p.lesson_steps)
    sampled_at = time.monotonic()
    now = engine.paused_at if engine.paused else sampled_at
    elapsed = now-engine.run_at
    phase = engine._phase(now)
    live_marks = engine._live_feedback(elapsed) if phase == "playing" else []
    visual_motion = engine._visual_motion(now)
    lesson = build_lesson_snapshot(
        p, ex, variant, fingerprint=engine.fingerprint,
        warmup=engine.is_builtin_warmup, lesson_steps=lesson_steps)
    tempo_map = engine._active_tempo_map()
    # Local-zero source timing followed by the explicit practice-BPM
    # silence. These exact segments are sent to Godot and retained
    # through the automatic-rest phase with the same run_at timestamp.
    visual_segments = ()
    tempo_segments = ()
    if tempo_map is not None:
        local_map = tempo_map.from_beat(engine.play_from_beat)
        tempo_segments = local_map.as_segments()
        visual_segments = (*tempo_segments, {
            "start_beat": local_map.duration_beats,
            "end_beat": local_map.duration_beats+engine.visual_gap_beats,
            "bpm": float(p.bpm),
            "start_seconds": local_map.duration_seconds,
        })
    timing = TimingSnapshot(
        sampled_at=sampled_at, now=now, run_at=engine.run_at,
        tempo_segments=tempo_segments,
        visual_tempo_segments=visual_segments,
        visual_preparation_schedule=engine.visual_transport.preparation_schedule(),
        mapped_clock_beat=(engine._elapsed_beat(now-engine.run_at)
                           if tempo_map is not None else None),
        running=engine.running, paused=engine.paused, auto=engine.auto,
        preview_only=engine.preview_only, play_from_beat=engine.play_from_beat,
        open_from_beat=engine.open_from_beat, pending_rewind=engine.pending_rewind,
        review_end_beat=engine.review_end_beat,
        awaiting_score_revision=engine.awaiting_score_revision,
        count_in_beats=engine.count_in_beats,
        count_in_bar_beats=engine.count_in_bar_beats, count_in_meter=engine.count_in_meter,
        midi_notes=len(engine.recorder.presses) if engine.recorder is not None else 0,
        visual_offset_beats=engine.visual_offset_beats,
        visual_gap_beats=engine.visual_gap_beats, visual_motion=visual_motion,
        practice_timeline=practice_timeline, practice_preparation=engine.practice_preparation,
        take_result=({"clean": bool(engine.pending_result.clean),
                      "correct": engine.pending_result.correct,
                      "total": len(engine.pending_result.notes)}
                     if engine.mode == "practice" and engine.pending_result is not None else None),
        feedback_marks=engine.feedback_marks, live_marks=live_marks,
        feedback_unmapped=engine.feedback_unmapped,
        scoring_available=(not engine.preview_only and engine.midi.connected
                           and engine.mode in ("practice", "perform")),
    )
    guided = None
    if engine.mode == "learn" and engine.teaching is not None:
        teaching = engine.teaching.snapshot(now=time.monotonic())
        phrase = engine.display_phrase()
        guided = GuidedSnapshot(
            teaching=teaching,
            fragment={"first_bar": phrase.first_bar, "last_bar": phrase.last_bar,
                      "start_beat": engine.guided_range[0], "end_beat": engine.guided_range[1]},
            phase=engine._phase(now),
            has_more_units=activity.learner["next_unit"] is not None and engine._guided_return is None,
            returning=bool(engine._guided_return),
            required_notes=(len(engine._remediation_active.variant.notes)
                            if engine._remediation_active is not None
                            else len(phrase.notes)),
            duration_beats=phrase.end-phrase.start,
            feedback_marks=engine._guided_marks(teaching),
        )
    return SessionSnapshot(mode=engine.mode, feedback=engine.feedback,
        device=engine.midi.device, revision=engine.score_revision,
        transport_id=engine.transport_id, phase=phase, activity=activity,
        lesson=lesson, timing=timing, guided=guided)


"""The versioned contract of the per-frame state snapshot sent to Godot.

The snapshot is the UI's main input: about a hundred keys polled every
frame. This module is its single declaration -- every key and the JSON kinds
its value may take. Python tests check real snapshots against it in every
phase; scripts/generate_state_contract.py writes the same table to
godot/state_contract.gd, which validates snapshots in debug builds. A key
rename or type change therefore fails a test on both sides instead of being
silently replaced by a GDScript .get() default.

Bump VERSION whenever a key is removed, renamed or changes meaning.
"""
from __future__ import annotations

VERSION = 2

# Values that do not change frame to frame. They travel in command replies
# (library.open, practice.command, ...) and are omitted from state.snapshot.
STATIC_KEYS = ("import_warnings",)

KINDS = ("bool", "number", "string", "list", "dict", "null")

SCHEMA: dict[str, tuple[str, ...]] = {
    "auto": ('bool',),
    "automatic_tempo_steps": ('number',),
    "awaiting_score_revision": ('null', 'number'),
    "beat": ('number',),
    "bpm": ('number',),
    "can_decrease_tempo": ('bool',),
    "can_increase_tempo": ('bool',),
    "clean_runs_required": ('number',),
    "clock_beat": ('number',),
    "clock_elapsed_seconds": ('number',),
    "clock_sampled_at_ms": ('number',),
    "count_in_bar_beats": ('number',),
    "count_in_beats": ('number',),
    "count_in_meter": ('list',),
    "countdown": ('number',),
    "current_bar": ('number',),
    "demo": ('dict', 'null'),
    "device": ('string',),
    "duration": ('number',),
    "duration_beats": ('number',),
    "effective_bpm": ('number',),
    "exercise": ('number',),
    "exercise_count": ('number',),
    "exercise_strategy": ('string',),
    "feedback": ('string',),
    "feedback_marks": ('list',),
    "feedback_unmapped": ('number',),
    "fingering": ('dict', 'null'),
    "first_bar": ('number',),
    "guided_recovery": ('bool',),
    "hand": ('string',),
    "hand_stages": ('list',),
    "hands": ('list',),
    "hints_enabled": ('bool',),
    "import_warnings": ('list',),
    "key_fifths": ('number',),
    "kind": ('string',),
    "last_bar": ('number',),
    "lead_in_bars": ('number',),
    "learner": ('dict', 'null'),
    "lesson_level": ('string',),
    "lesson_level_count": ('number',),
    "lesson_level_number": ('number',),
    "lesson_step": ('number',),
    "lesson_steps": ('number',),
    "lesson_steps_mastered": ('number',),
    "live_note_feedback": ('dict', 'null'),
    "loaded": ('bool',),
    "manual_tempo_step_bpm": ('number',),
    "mastered": ('number',),
    "maximum_bpm": ('number',),
    "measure_boundaries": ('list',),
    "metronome": ('bool',),
    "midi_calibration": ('dict',),
    "midi_held_pitches": ('list',),
    "midi_input_age": ('null', 'number'),
    "midi_input_count": ('number',),
    "midi_input_note": ('null', 'number'),
    "midi_key_range": ('dict',),
    "midi_next_pitches": ('list',),
    "midi_notes": ('number',),
    "midi_offset_ms": ('number',),
    "midi_recent_keys": ('list',),
    "minimum_bpm": ('number',),
    "mistake_response_strategy": ('string',),
    "mode": ('string',),
    "next_action": ('string',),
    "next_count_in_beats": ('number',),
    "next_count_in_meter": ('list',),
    "short_rest_latency_seconds": ('number',),
    "original_bpm": ('number',),
    "pause_context": ('null', 'string'),
    "paused": ('bool',),
    "performance_summary": ('dict', 'null'),
    "phase": ('string',),
    "piece_fingerprint": ('string',),
    "piece_last_bar": ('number',),
    "placement_available": ('bool',),
    "play_from_beat": ('number',),
    "practice_preparation": ('dict', 'null'),
    "practice_timeline": ('dict',),
    "preview_only": ('bool',),
    "progress": ('number',),
    "recovery_beat": ('null', 'number'),
    "recovery_notice": ('dict', 'null'),
    "required_notes": ('number',),
    "resume_count_in_beat": ('null', 'number'),
    "retry_range": ('dict', 'null'),
    "review_range": ('dict', 'null'),
    "revision": ('number',),
    "running": ('bool',),
    "schema_version": ('number',),
    "score_loop_enabled": ('bool',),
    "score_queue_next": ('dict', 'null'),
    "scoring_available": ('bool',),
    "seek_available": ('bool',),
    "seek_range": ('dict', 'null'),
    "selected_start_bar": ('number',),
    "skip_available": ('bool',),
    "stage_change": ('string',),
    "stage_family": ('string',),
    "stage_label": ('string',),
    "stage_meaningful": ('bool',),
    "start_bpm": ('number',),
    "streak": ('number',),
    "take_result": ('dict', 'null'),
    "target_bpm": ('number',),
    "teaching": ('dict', 'null'),
    "tempo_rungs": ('list',),
    "tempo_segments": ('list',),
    "title": ('string',),
    "transition_in_seconds": ('null', 'number'),
    "transport_id": ('number',),
    "visual_gap_beats": ('number',),
    "visual_offset_beats": ('number',),
    "visual_preparation_schedule": ('dict', 'null'),
    "visual_run_at_ms": ('number',),
    "tempo_epoch_ms": ('number',),
    "visual_scroll_beat": ('number',),
    "visual_scroll_speed": ('number',),
    "visual_target_beat": ('number',),
    "visual_tempo_segments": ('list',),
    "warmup": ('bool',),
}


def kind_of(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def problems(state: dict) -> list[str]:
    """Contract violations of one snapshot (empty when it conforms)."""
    found = []
    for key, value in state.items():
        allowed = SCHEMA.get(key)
        if allowed is None:
            found.append(f"unknown key {key!r}")
        elif kind_of(value) not in allowed:
            found.append(f"{key!r} is {kind_of(value)}, expected {'|'.join(allowed)}")
    return found

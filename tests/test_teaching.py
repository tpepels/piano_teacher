"""Guided learning recognizes fresh physical attacks without a song clock."""
from dataclasses import FrozenInstanceError

import pytest

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Note, Phrase
from piano_teacher.teaching import TeachingConfig, TeachingController


def variant(notes, *, start=16.0, end=24.0, indices=None):
    events = tuple(Note(start + beat, start + beat + length, pitch, i, 0, hand)
                   for i, (beat, pitch, length, hand) in enumerate(notes))
    return ExerciseVariant("original", Phrase(3, 5, 6, start, end, events),
                           tuple(range(len(events))) if indices is None else indices)


def controller(notes=None, *, config=None, connected=True):
    if notes is None:
        notes = [(0, 60, .5, "right"), (1, 62, .5, "right")]
    lesson = variant(notes)
    guided = TeachingController(config=config or TeachingConfig())
    guided.bind(stage_key="piece:3:right:original", revision=9, variant=lesson,
                fragment_start=0, fragment_end=8, now=10, connected=connected)
    return guided


def press(guided, pitch, at, channel=0):
    guided.receive(pitch=pitch, is_on=True, channel=channel, at=at)


def release(guided, pitch, at, channel=0):
    guided.receive(pitch=pitch, is_on=False, channel=channel, at=at)


def test_binding_retains_source_identity_and_fragment_local_beats():
    lesson = variant([(0, 48, 8, "left"), (4, 60, 1, "right"),
                      (4, 60, 2, "left"), (6, 64, .5, "right"),
                      (8, 67, .5, "right")], indices=(2, 7, 8, 10, 12))
    guided = TeachingController()
    guided.bind(stage_key="stage", revision=4, variant=lesson,
                fragment_start=4, fragment_end=8, now=0, connected=True)
    state = guided.snapshot(now=0)
    assert state["phase"] == "introducing"
    assert state["revision"] == 4
    assert state["target_count"] == 2
    assert state["expected_notes"] == [
        {"id": "stage:7", "pitch": 60, "label": "C4", "beat": 0,
         "source_beat": 20, "end_beat": 1, "hand": "right"},
        {"id": "stage:8", "pitch": 60, "label": "C4", "beat": 0,
         "source_beat": 20, "end_beat": 2, "hand": "left"},
    ]
    assert state["mastery_eligible"] is False


def test_start_is_required_and_slow_correct_attacks_follow_target_order():
    guided = controller()
    press(guided, 60, 10.1)
    assert guided.snapshot(now=10.1)["target_index"] == 0
    release(guided, 60, 10.2)
    guided.start(now=11)
    assert guided.snapshot(now=11)["phase"] == "guided_wait"
    guided.tick(now=100)
    assert guided.snapshot(now=100)["target_index"] == 0
    press(guided, 62, 101)
    assert guided.snapshot(now=101)["target_index"] == 0
    release(guided, 62, 102)
    press(guided, 60, 103)
    assert guided.snapshot(now=103)["target_index"] == 1
    press(guided, 62, 500)
    state = guided.snapshot(now=500)
    assert state["phase"] == "guided_complete"
    assert state["completed"] is True
    assert state["expected_notes"] == []
    assert state["mastery_eligible"] is False


def test_chord_requires_all_pitches_down_within_configured_window():
    guided = controller([(0, 60, 1, "right"), (0, 64, 1, "right"),
                         (0, 67, 1, "right")],
                        config=TeachingConfig(chord_window_seconds=.4))
    guided.start(now=10)
    press(guided, 60, 10.1)
    press(guided, 64, 10.3)
    assert guided.snapshot(now=10.3)["target_index"] == 0
    press(guided, 67, 10.5)
    state = guided.snapshot(now=10.5)
    assert state["completed"] is True
    assert [n["status"] for n in state["note_feedback"]] == ["correct"] * 3


def test_releasing_a_chord_candidate_requires_a_new_attack():
    guided = controller([(0, 60, 1, "right"), (0, 64, 1, "right")])
    guided.start(now=10)
    press(guided, 60, 10.1)
    release(guided, 60, 10.15)
    press(guided, 64, 10.2)
    assert guided.snapshot(now=10.2)["target_index"] == 0
    press(guided, 60, 10.3)
    assert guided.snapshot(now=10.3)["completed"] is True


def test_expired_chord_does_not_combine_stale_held_keys():
    guided = controller([(0, 60, 1, "right"), (0, 64, 1, "right")])
    guided.start(now=10)
    press(guided, 60, 10.1)
    guided.tick(now=11)
    press(guided, 64, 11.1)
    press(guided, 60, 11.15)  # Duplicate note-on is not a fresh attack.
    assert guided.snapshot(now=11.15)["target_index"] == 0
    release(guided, 60, 11.16)
    press(guided, 60, 11.2)
    assert guided.snapshot(now=11.2)["completed"] is True


def test_next_chord_cannot_reuse_an_accepted_held_pitch():
    guided = controller([(0, 60, 4, "right"), (1, 60, 1, "right"),
                         (1, 64, 1, "right")])
    guided.start(now=10)
    press(guided, 60, 10.1)
    press(guided, 64, 10.2)
    press(guided, 60, 10.21)
    assert guided.snapshot(now=10.21)["target_index"] == 1
    release(guided, 60, 10.22)
    press(guided, 60, 10.25)
    assert guided.snapshot(now=10.25)["completed"] is True


def test_long_accepted_key_may_remain_held_while_new_pitches_are_taught():
    guided = controller([(0, 48, 8, "left"), (1, 60, 1, "right"),
                         (2, 62, 1, "right")])
    guided.start(now=10)
    press(guided, 48, 10.1)
    press(guided, 60, 25)
    press(guided, 62, 40)
    assert guided.snapshot(now=40)["completed"] is True
    assert guided.snapshot(now=40)["heard_pitches"] == [48, 60, 62]


def test_repeated_pitch_requires_release_then_reattack():
    guided = controller([(0, 60, .5, "right"), (1, 60, .5, "right")])
    guided.start(now=10)
    press(guided, 60, 10.1)
    press(guided, 60, 11)
    assert guided.snapshot(now=11)["target_index"] == 1
    release(guided, 60, 11.1)
    press(guided, 60, 12)
    assert guided.snapshot(now=12)["completed"] is True


def test_single_unison_attack_preserves_both_distinct_source_note_ids():
    guided = controller([(0, 60, 1, "left"), (0, 60, 2, "right")])
    guided.start(now=10)
    press(guided, 60, 10.1)
    state = guided.snapshot(now=10.1)
    assert state["completed"] is True
    assert [(n["id"], n["pitch"], n["status"]) for n in state["note_feedback"]] == [
        ("piece:3:right:original:0", 60, "correct"),
        ("piece:3:right:original:1", 60, "correct"),
    ]


def test_wrong_key_shows_hint_and_correction_replaces_wrong_with_assisted():
    guided = controller()
    guided.start(now=10)
    assert guided.snapshot(now=10)["hint_visible"] is False
    press(guided, 61, 10.1)
    state = guided.snapshot(now=10.1)
    assert state["hint_visible"] is True
    assert state["hint_reason"] == "wrong_note"
    assert state["heard_pitches"] == [61]
    assert state["note_feedback"] == [
        {"id": "piece:3:right:original:0", "pitch": 61, "beat": 0,
         "status": "wrong", "hint_used": True}]
    press(guided, 60, 10.2)
    state = guided.snapshot(now=10.2)
    assert state["target_index"] == 1
    assert state["hint_visible"] is False
    assert state["note_feedback"] == [
        {"id": "piece:3:right:original:0", "pitch": 60, "beat": 0,
         "status": "assisted", "hint_used": True}]
    press(guided, 60, 10.3)  # Neither duplicate nor held wrong keys advance.
    assert guided.snapshot(now=10.3)["target_index"] == 1
    press(guided, 62, 10.4)
    state = guided.snapshot(now=10.4)
    assert state["completed"] is True
    assert [n["status"] for n in state["note_feedback"]] == ["assisted", "correct"]


def test_stall_is_configurable_and_polling_never_advances_a_target():
    guided = controller(config=TeachingConfig(stall_seconds=2))
    guided.start(now=10)
    guided.tick(now=11.99)
    assert guided.snapshot(now=11.99)["hint_visible"] is False
    guided.tick(now=12)
    state = guided.snapshot(now=12)
    assert state["hint_visible"] is True
    assert state["hint_reason"] == "stall"
    assert state["target_index"] == 0
    assert state["note_feedback"] == []
    press(guided, 60, 100)
    assert guided.snapshot(now=100)["note_feedback"][0]["status"] == "assisted"
    assert guided.snapshot(now=100)["hint_visible"] is False


def test_persistent_hint_toggle_remembers_assistance_for_the_current_target():
    guided = controller(config=TeachingConfig(persistent_hints=True))
    guided.start(now=10)
    assert guided.snapshot(now=10)["hint_reason"] == "persistent"
    guided.set_hints(False, now=10.1)
    assert guided.snapshot(now=10.1)["hint_visible"] is False
    press(guided, 60, 10.2)
    assert guided.snapshot(now=10.2)["note_feedback"][0]["status"] == "assisted"
    guided.set_hints(True, now=10.3)
    assert guided.snapshot(now=10.3)["hint_visible"] is True
    press(guided, 62, 10.4)
    state = guided.snapshot(now=10.4)
    assert state["hint_visible"] is False
    assert [n["status"] for n in state["note_feedback"]] == ["assisted", "assisted"]


def test_turning_off_persistent_hints_preserves_contextual_wrong_note_help():
    guided = controller(config=TeachingConfig(persistent_hints=True))
    guided.start(now=10)
    press(guided, 70, 10.1)
    guided.set_hints(False, now=10.2)
    state = guided.snapshot(now=10.2)
    assert state["hint_visible"] is True
    assert state["hint_reason"] == "wrong_note"


def test_pause_freezes_stall_duration_and_resume_requires_fresh_attacks():
    guided = controller([(0, 60, 1, "right"), (0, 64, 1, "right")])
    guided.start(now=10)
    press(guided, 60, 10.1)
    guided.pause(now=11)
    state = guided.snapshot(now=100)
    assert state["phase"] == "paused"
    assert state["heard_pitches"] == []
    assert state["hint_visible"] is False
    press(guided, 64, 100.1)
    guided.resume(now=101)
    press(guided, 60, 101.1)  # A duplicate of the physically held key.
    assert guided.snapshot(now=101.1)["target_index"] == 0
    assert guided.snapshot(now=102.9)["hint_visible"] is False
    release(guided, 60, 102.91)
    release(guided, 64, 102.92)
    press(guided, 60, 102.93)
    press(guided, 64, 102.94)
    state = guided.snapshot(now=102.94)
    assert state["completed"] is True
    assert [n["status"] for n in state["note_feedback"]] == ["correct", "correct"]


def test_pause_preserves_existing_hint_and_elapsed_stall_on_resume():
    guided = controller()
    guided.start(now=10)
    guided.pause(now=12)
    guided.resume(now=100)
    assert guided.snapshot(now=100.99)["hint_visible"] is False
    assert guided.snapshot(now=101)["hint_reason"] == "stall"
    guided.pause(now=101.1)
    guided.resume(now=200)
    press(guided, 60, 200.1)
    assert guided.snapshot(now=200.1)["note_feedback"][0]["status"] == "assisted"


def test_disconnect_blocks_input_and_reconnect_requires_explicit_start():
    guided = controller()
    guided.start(now=10)
    press(guided, 60, 10.1)
    guided.set_connected(False, now=10.2)
    press(guided, 62, 10.3)
    guided.start(now=10.4)
    state = guided.snapshot(now=10.4)
    assert state["phase"] == "disconnected"
    assert state["completed"] is False
    assert state["heard_pitches"] == []
    guided.set_connected(True, now=11)
    assert guided.snapshot(now=11)["phase"] == "ready"
    press(guided, 62, 11.1)
    assert guided.snapshot(now=11.1)["completed"] is False
    release(guided, 62, 11.2)
    guided.start(now=12)
    assert guided.snapshot(now=12)["target_index"] == 0
    assert guided.snapshot(now=12)["note_feedback"] == []
    press(guided, 60, 12.1)
    press(guided, 62, 12.2)
    assert guided.snapshot(now=12.2)["completed"] is True


def test_start_without_device_is_blocked_and_connection_polling_is_idempotent():
    guided = controller(connected=False)
    guided.start(now=10)
    press(guided, 60, 10.1)
    assert guided.snapshot(now=10.1)["phase"] == "disconnected"
    guided.set_connected(True, now=11)
    guided.start(now=11.1)
    press(guided, 60, 11.2)
    guided.set_connected(True, now=11.3)
    assert guided.snapshot(now=11.3)["phase"] == "guided_wait"
    assert guided.snapshot(now=11.3)["target_index"] == 1


def test_stop_clears_guided_attempt_and_requires_a_new_start():
    guided = controller()
    guided.start(now=10)
    press(guided, 60, 10.1)
    guided.stop()
    press(guided, 62, 10.2)
    state = guided.snapshot(now=10.2)
    assert state["phase"] == "ready"
    assert state["target_index"] == 0
    assert state["note_feedback"] == []
    assert state["hint_visible"] is False
    release(guided, 60, 10.3)
    release(guided, 62, 10.3)
    guided.start(now=11)
    press(guided, 60, 11.1)
    assert guided.snapshot(now=11.1)["target_index"] == 1


def test_rebind_discards_old_feedback_candidates_and_obsolete_input():
    guided = controller()
    guided.start(now=10)
    press(guided, 61, 10.1)
    guided.bind(stage_key="other", revision=10,
                variant=variant([(0, 65, 1, "right")]),
                fragment_start=0, fragment_end=4, now=20, connected=True)
    guided.start(now=20.1)
    press(guided, 65, 10.2)  # Event captured before the current binding.
    assert guided.snapshot(now=20.1)["target_index"] == 0
    assert guided.snapshot(now=20.1)["note_feedback"] == []
    press(guided, 65, 20.2)
    state = guided.snapshot(now=20.2)
    assert state["revision"] == 10
    assert state["completed"] is True
    assert state["note_feedback"][0]["id"] == "other:0"


@pytest.mark.parametrize("pitch,channel", [(-1, 0), (128, 0), (60, 9), (60, -1), (60, 16)])
def test_invalid_or_percussion_input_does_not_change_guided_state(pitch, channel):
    guided = controller()
    guided.start(now=10)
    press(guided, pitch, 10.1, channel=channel)
    state = guided.snapshot(now=10.1)
    assert state["target_index"] == 0
    assert state["heard_pitches"] == []
    assert state["note_feedback"] == []
    assert state["hint_visible"] is False


def test_channel_specific_releases_do_not_free_another_channels_held_key():
    guided = controller([(0, 60, .5, "right"), (1, 60, .5, "right")])
    guided.start(now=10)
    press(guided, 60, 10.1, channel=1)
    press(guided, 60, 10.2, channel=2)
    release(guided, 60, 10.3, channel=2)
    press(guided, 60, 10.4, channel=2)
    assert guided.snapshot(now=10.4)["target_index"] == 1
    release(guided, 60, 10.5, channel=1)
    release(guided, 60, 10.6, channel=2)
    press(guided, 60, 10.7, channel=2)
    assert guided.snapshot(now=10.7)["completed"] is True


def test_empty_fragment_completes_only_when_started_without_mastery():
    guided = TeachingController()
    guided.bind(stage_key="empty", revision=1,
                variant=variant([(0, 60, 8, "right")]),
                fragment_start=4, fragment_end=8, now=0, connected=True)
    assert guided.snapshot(now=0)["completed"] is False
    guided.start(now=1)
    state = guided.snapshot(now=1)
    assert state["phase"] == "guided_complete"
    assert state["target_count"] == 0
    assert state["mastery_eligible"] is False


def test_hint_setting_does_not_mutate_reusable_frozen_config():
    config = TeachingConfig()
    guided = controller(config=config)
    guided.start(now=10)
    guided.set_hints(True, now=10.1)
    assert config.persistent_hints is False
    with pytest.raises(FrozenInstanceError):
        config.persistent_hints = True


def test_stage_switch_cannot_reuse_a_physically_held_key():
    guided = controller([(0, 60, 1, "right")])
    guided.start(now=10)
    press(guided, 60, 10.1)
    guided.bind(stage_key="other", revision=10,
                variant=variant([(0, 60, 1, "right")]),
                fragment_start=0, fragment_end=4, now=11, connected=True)
    guided.start(now=11.1)
    press(guided, 60, 11.2)
    assert guided.snapshot(now=11.2)["completed"] is False
    assert guided.snapshot(now=11.2)["heard_pitches"] == []
    release(guided, 60, 11.3)
    press(guided, 60, 11.4)
    assert guided.snapshot(now=11.4)["completed"] is True


def test_assisted_count_counts_onset_targets_and_completion_reports_help_used():
    guided = controller([(0, 60, 1, "left"), (0, 60, 1, "right"),
                         (0, 64, 1, "right"), (1, 62, 1, "right")])
    guided.start(now=10)
    state = guided.snapshot(now=10)
    assert state["assisted_count"] == 0
    assert state["completion"] is None
    press(guided, 70, 10.1)
    press(guided, 60, 10.2)
    press(guided, 64, 10.3)
    state = guided.snapshot(now=10.3)
    assert state["assisted_count"] == 1  # One target, three source notes.
    assert state["completion"] is None
    press(guided, 62, 10.4)
    state = guided.snapshot(now=10.4)
    assert state["assisted_count"] == 1
    assert state["completion"] == "assisted"
    guided.stop()
    state = guided.snapshot(now=10.5)
    assert state["assisted_count"] == 0
    assert state["completion"] is None


def test_unassisted_completion_does_not_claim_mastery():
    guided = controller()
    guided.start(now=10)
    press(guided, 60, 10.1)
    press(guided, 62, 10.2)
    state = guided.snapshot(now=10.2)
    assert state["assisted_count"] == 0
    assert state["completion"] == "unassisted"
    assert state["mastery_eligible"] is False


def test_out_of_order_chord_events_still_respect_total_attack_span():
    guided = controller([(0, 60, 1, "right"), (0, 64, 1, "right")])
    guided.start(now=10)
    press(guided, 60, 11)
    press(guided, 64, 10.5)
    assert guided.snapshot(now=11)["completed"] is False
    release(guided, 60, 11.1)
    release(guided, 64, 11.1)
    press(guided, 60, 11.2)
    press(guided, 64, 11.3)
    assert guided.snapshot(now=11.3)["completed"] is True


@pytest.mark.parametrize("paused", [False, True], ids=["start", "resume"])
def test_delayed_release_from_before_transition_allows_next_real_attack(paused):
    guided = controller()
    if paused:
        guided.start(now=10)
        press(guided, 62, 10.1)  # Retained as a physical key while paused.
        guided.pause(now=10.15)
        guided.resume(now=10.3)
        release(guided, 62, 10.2)
        press(guided, 60, 10.4)
        press(guided, 62, 10.5)
        assert guided.snapshot(now=10.5)["completed"] is True
    else:
        press(guided, 60, 10.1)
        guided.start(now=10.3)
        release(guided, 60, 10.2)
        press(guided, 60, 10.4)
        assert guided.snapshot(now=10.4)["target_index"] == 1


def test_obsolete_release_cannot_clear_a_newer_chord_candidate():
    guided = controller([(0, 60, 1, "right"), (0, 64, 1, "right")])
    guided.start(now=10)
    press(guided, 60, 10.1)
    release(guided, 60, 10.2)
    press(guided, 60, 10.3)
    release(guided, 60, 10.15)  # Delayed release belongs to the older press.
    press(guided, 64, 10.4)
    assert guided.snapshot(now=10.4)["completed"] is True


def test_delayed_note_on_before_start_still_cannot_progress_or_latch_a_key():
    guided = controller()
    guided.start(now=10.3)
    press(guided, 60, 10.2)
    state = guided.snapshot(now=10.3)
    assert state["target_index"] == 0
    assert state["heard_pitches"] == []
    press(guided, 60, 10.4)
    assert guided.snapshot(now=10.4)["target_index"] == 1

"""Live MIDI previews are immediate, bounded, and never grade held duration."""
from piano_teacher.live_input_view import LiveInputView
from piano_teacher.music import Note, Phrase


def _phrase():
    return Phrase(1, 1, 2, 0.0, 8.0, (
        Note(0.0, 2.0, 60, 0, 0, "right", "attack-a"),
        Note(0.0, 2.0, 64, 0, 0, "right", "attack-b"),
        Note(2.0, 4.0, 60, 0, 0, "right", "attack-c"),
        Note(4.0, 6.0, 48, 1, 0, "left", "attack-left"),
    ))


def _send(view, pitch, now, **overrides):
    args = dict(pitch=pitch, is_on=True, now=now, phrase=_phrase(),
                hand="right", bpm=60, from_beat=0.0, run_at=10.0,
                running=True, paused=False, preview=False,
                mode="practice", transport_id=4)
    args.update(overrides)
    view.receive(**args)


def _last(view, now=10.1):
    return view.snapshot(now=now, phrase=_phrase(), hand="right",
                         beat=0.0, playing=True)["midi_visual_events"][-1]


def test_chord_presses_are_independently_visible_and_provisional():
    view = LiveInputView()
    _send(view, 60, 10.03)
    _send(view, 64, 10.04)
    assert [event["source_id"] for event in view.events] == ["attack-a", "attack-b"]
    assert [event["status"] for event in view.events] == ["on_time", "on_time"]
    assert view.snapshot(now=10.05, phrase=_phrase(), hand="right", beat=0.0,
                         playing=True)["midi_held_pitches"] == [60, 64]
    view.receive(pitch=60, is_on=False, now=10.06, phrase=_phrase(),
                 hand="right", bpm=60, from_beat=0, run_at=10,
                 running=True, paused=False, preview=False,
                 mode="practice", transport_id=4)
    snapshot = view.snapshot(now=10.07, phrase=_phrase(), hand="right",
                             beat=0.0, playing=True)
    assert snapshot["midi_held_pitches"] == [64]
    assert len(snapshot["midi_visual_events"]) == 2  # short taps survive poll


def test_early_late_and_wrong_notes_are_separate_from_final_grading():
    view = LiveInputView()
    _send(view, 60, 9.8)  # count-in is visible, never claims success
    assert _last(view, 9.81)["status"] == "count_in"
    _send(view, 60, 10.20)
    assert _last(view, 10.21)["status"] == "late"
    _send(view, 61, 10.25)
    assert _last(view, 10.26)["status"] == "unexpected"
    _send(view, 60, 11.80)
    assert _last(view, 11.81)["status"] == "early"
    assert _last(view, 11.81)["source_id"] == "attack-c"


def test_piano_disconnect_clears_held_and_attempt_restart_clears_matches():
    view = LiveInputView()
    _send(view, 60, 10.01)
    view.reset_attempt()
    assert view.held == {60: 1}
    _send(view, 60, 20.01, run_at=20.0, transport_id=5)
    assert _last(view, 20.02)["source_id"] == "attack-a"
    view.clear_device()
    assert view.held == {}
    assert not view.events


def test_preview_and_paused_keys_do_not_claim_accuracy():
    view = LiveInputView()
    _send(view, 60, 10.05, preview=True)
    assert _last(view)["status"] == "heard"
    _send(view, 64, 10.06, paused=True)
    assert _last(view)["status"] == "heard"
    assert not view.used


def test_lookahead_follows_active_hand_and_forgets_stale_events():
    view = LiveInputView()
    _send(view, 48, 14.0, hand="left")
    left = view.snapshot(now=14.1, phrase=_phrase(), hand="left",
                         beat=4.0, playing=True)
    assert left["midi_next_pitches"] == [48]
    assert left["midi_visual_events"]
    right = view.snapshot(now=16.0, phrase=_phrase(), hand="right",
                          beat=2.0, playing=True)
    assert right["midi_next_pitches"] == [60]
    assert right["midi_visual_events"] == []


def test_repeated_overlapping_same_pitch_tracks_held_counts():
    view = LiveInputView()
    _send(view, 60, 10.0)
    _send(view, 60, 10.02)
    assert view.held[60] == 2
    view.receive(pitch=60, is_on=False, now=10.10, phrase=None, hand="both",
                 bpm=60, from_beat=0, run_at=0, running=False, paused=False,
                 preview=False, mode="practice", transport_id=1)
    assert view.held[60] == 1


def test_wrong_key_is_tethered_to_nearby_actual_chord_notation():
    view = LiveInputView()
    _send(view, 61, 10.04)
    event = _last(view, 10.05)
    assert event["status"] == "unexpected"
    assert event["source_id"] == ""
    assert event["reference_source_id"] == "attack-a"
    assert view.used == set()  # wrong pitch cannot consume a right note
    _send(view, 60, 10.08)
    assert _last(view, 10.09)["source_id"] == "attack-a"


def test_random_wrong_pitch_in_a_rest_does_not_invent_notation():
    view = LiveInputView()
    _send(view, 77, 11.0)  # no required attack at this musical time
    event = _last(view, 11.01)
    assert event["status"] == "unexpected"
    assert event["reference_source_id"] == ""


def test_wrong_chord_pitch_with_both_hands_uses_closest_real_reference():
    view = LiveInputView()
    _send(view, 49, 14.02, hand="both")
    event = _last(view, 14.03)
    assert event["status"] == "unexpected"
    assert event["reference_source_id"] == "attack-left"

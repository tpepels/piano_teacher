"""Live MIDI previews are immediate, bounded, and never grade the take."""
from piano_teacher.live_input_view import LiveInputView
from piano_teacher.exercise_contracts import TempoMap, TempoSegment
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
    return view.receive(**args)


def _release(view, pitch, now, **overrides):
    return _send(view, pitch, now, is_on=False, **overrides)


def _last(view, now=10.1):
    return view.snapshot(now=now, phrase=_phrase(), hand="right",
                         beat=0.0, playing=True)["midi_recent_keys"][-1]


def test_chord_presses_are_independently_visible_and_provisional():
    view = LiveInputView()
    first = _send(view, 60, 10.03)
    second = _send(view, 64, 10.04)
    assert [first["kind"], second["kind"]] == ["attack", "attack"]
    assert [first["source_id"], second["source_id"]] == ["attack-a", "attack-b"]
    assert [first["status"], second["status"]] == ["on_time", "on_time"]
    assert "sequence" not in first  # only the engine's event log sequences
    assert view.snapshot(now=10.05, phrase=_phrase(), hand="right", beat=0.0,
                         playing=True)["midi_held_pitches"] == [60, 64]
    view.receive(pitch=60, is_on=False, now=10.06, phrase=_phrase(),
                 hand="right", bpm=60, from_beat=0, run_at=10,
                 running=True, paused=False, preview=False,
                 mode="practice", transport_id=4)
    snapshot = view.snapshot(now=10.07, phrase=_phrase(), hand="right",
                             beat=0.0, playing=True)
    assert snapshot["midi_held_pitches"] == [64]
    assert len(snapshot["midi_recent_keys"]) == 2  # short taps survive poll


def test_early_late_and_wrong_notes_are_separate_from_final_grading():
    view = LiveInputView()
    _send(view, 60, 9.8)  # count-in is visible, never claims success
    assert _last(view, 9.81)["status"] == "count_in"
    _send(view, 60, 10.25)
    assert _last(view, 10.26)["status"] == "late"
    _send(view, 61, 10.25)
    assert _last(view, 10.26)["status"] == "unexpected"
    _send(view, 60, 11.65)
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
    assert not view.recent


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
    assert left["midi_recent_keys"]
    right = view.snapshot(now=16.0, phrase=_phrase(), hand="right",
                          beat=2.0, playing=True)
    assert right["midi_next_pitches"] == [60]
    assert right["midi_recent_keys"] == []


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


def test_provisional_midi_feedback_uses_shaped_grading_clock():
    """A constant-BPM onset would call these late or unexpected."""
    shaped = TempoMap("two-phase", (
        TempoSegment(0, 2, 30),
        TempoSegment(2, 8, 60),
    ))
    view = LiveInputView()
    _send(view, 60, 14.0, tempo_map=shaped)
    assert _last(view, 14.01)["source_id"] == "attack-c"
    assert _last(view, 14.01)["status"] == "on_time"
    view.reset_attempt()
    _send(view, 60, 13.65, tempo_map=shaped)
    assert _last(view, 13.81)["source_id"] == "attack-c"
    assert _last(view, 13.81)["status"] == "early"
    view.reset_attempt()
    _send(view, 60, 14.35, tempo_map=shaped)
    assert _last(view, 14.36)["source_id"] == "attack-c"
    assert _last(view, 14.36)["status"] == "late"
    view.reset_attempt()
    _send(view, 61, 14.01, tempo_map=shaped)
    assert _last(view, 14.02)["reference_source_id"] == "attack-c"
    assert not view.used


def test_provisional_tempo_mapping_respects_partial_retry_origin():
    shaped = TempoMap("two-phase", (
        TempoSegment(0, 2, 30),
        TempoSegment(2, 8, 60),
    ))
    view = LiveInputView()
    # A partial retry from beat 2 starts at zero elapsed seconds.
    _send(view, 60, 10.02, from_beat=2.0, tempo_map=shaped)
    assert _last(view, 10.03)["source_id"] == "attack-c"
    assert _last(view, 10.03)["status"] == "on_time"


def test_early_release_is_reported_on_key_up_and_bound_to_its_source():
    view = LiveInputView()
    _send(view, 60, 10.02)  # attack-a, expected to sound for 2 s at 60 BPM
    event = _release(view, 60, 10.60)
    assert event["kind"] == "release"
    assert event["source_id"] == "attack-a"
    assert event["release"] == "short"
    assert event["transport_id"] == 4
    assert abs(event["held_seconds"] - .58) < 1e-9
    assert event["expected_seconds"] == 2.0


def test_release_verdict_uses_the_graders_duration_tolerance():
    from piano_teacher.practice import PlayedNote, evaluate
    # 60 BPM, two-beat note: the grader allows +/-1.28 s of hold slack.
    for held, verdict in ((2.0, "on_time"), (.6, "short"), (3.4, "long")):
        view = LiveInputView()
        _send(view, 60, 10.0)
        assert _release(view, 60, 10.0 + held)["release"] == verdict
        phrase = _phrase()
        graded = evaluate(phrase, "right", 60, [PlayedNote(60, 0.0, held),
                                                PlayedNote(64, 0.0, 2.0),
                                                PlayedNote(60, 2.0, 4.0)])
        expected = {"on_time": "correct"}.get(verdict, verdict)
        assert graded.notes[0].status == expected


def test_overlapping_same_pitch_releases_pair_fifo_like_the_recorder():
    view = LiveInputView()
    _send(view, 60, 10.0)        # attack-a
    _send(view, 60, 12.0)        # attack-c, the repeated pitch
    first = _release(view, 60, 12.05)
    second = _release(view, 60, 12.5)
    assert (first["source_id"], first["release"]) == ("attack-a", "on_time")
    assert (second["source_id"], second["release"]) == ("attack-c", "short")


def test_unmatched_preview_paused_and_stale_releases_emit_nothing():
    view = LiveInputView()
    _send(view, 61, 10.0)  # wrong pitch: no source
    assert _release(view, 61, 10.4) is None
    _send(view, 60, 10.0, preview=True)
    assert _release(view, 60, 10.4) is None
    _send(view, 60, 10.0)
    assert _release(view, 60, 10.4, paused=True) is None
    _send(view, 64, 10.0)
    view.reset_attempt()  # a key held into the next take
    assert _release(view, 64, 20.4, run_at=20.0, transport_id=5) is None

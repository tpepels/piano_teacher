"""Grace attacks are optional input, never required score or mastery credit."""
import pytest

from piano_teacher.live_feedback import expired_attack_misses, settled_assessment
from piano_teacher.live_input_view import LiveInputView
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import Curriculum, PlayedNote, Recorder, evaluate


def phrase(start=8.0):
    return Phrase(2, 3, 4, start, start + 8, (
        Note(start + 1, start + 1.5, 60, 0, 0, "right", "main"),
    ))


def grace(**overrides):
    return dict(id="grace-1", kind="grace", anchor_id="main", beat=1.0,
                midi_pitch=62, staff="right", position="before") | overrides


def send(view, pitch=62, at=1.0, **overrides):
    args = dict(pitch=pitch, is_on=True, now=10 + at, phrase=phrase(),
                hand="right", bpm=60, from_beat=0.0, run_at=10.0,
                running=True, paused=False, preview=False,
                mode="practice", transport_id=1, optional_notes=(grace(),))
    view.receive(**(args | overrides))
    return view.events[-1]


@pytest.mark.parametrize("position", ["before", "after"])
def test_played_or_omitted_grace_never_enters_required_counts(position):
    required = [PlayedNote(60, 1, 1.5)]
    for played in (required, required + [PlayedNote(62, .96, 1.01)]):
        result = evaluate(phrase(), "right", 60, played,
                          optional_notes=(grace(position=position),))
        assert result.clean
        assert result.correct == len(result.notes) == 1
        assert result.extra_notes == 0
        assert result.unmatched_played == ()


def test_only_grace_leaves_required_missed_and_cannot_advance_mastery():
    result = evaluate(phrase(), "right", 60, [PlayedNote(62, 1, 1.1)],
                      optional_notes=(grace(),))
    assert [n.status for n in result.notes] == ["missed"]
    assert result.extra_notes == 0
    assert not result.clean
    curriculum = Curriculum(Piece("test", 60, phrase().notes, (phrase(),)))
    assert curriculum.completed(result) == "Repeat this passage"
    assert curriculum.clean_streak == 0


def test_required_exact_pitch_has_priority_over_same_pitch_grace():
    result = evaluate(phrase(), "right", 60, [PlayedNote(60, 1, 1.5)],
                      optional_notes=(grace(midi_pitch=60),))
    assert result.clean
    view = LiveInputView()
    event = send(view, pitch=60, optional_notes=(grace(midi_pitch=60),))
    assert (event["status"], event["source_id"]) == ("on_time", "main")


def test_required_wrong_pitch_and_real_extras_survive_optional_matching():
    played = [PlayedNote(62, 1, 1.1), PlayedNote(61, 1.01, 1.4),
              PlayedNote(75, 4, 4.2)]
    result = evaluate(phrase(), "right", 60, played, optional_notes=(grace(),))
    assert [(n.status, n.played_pitch) for n in result.notes] == [("wrong", 61)]
    assert result.unmatched_played == (played[2],)
    assert result.extra_notes == 1


def test_optional_identity_consumed_once_even_if_repeated_in_input_data():
    optional = (grace(), grace())
    played = [PlayedNote(60, 1, 1.5), PlayedNote(62, .98, 1.01),
              PlayedNote(62, 1.04, 1.08)]
    result = evaluate(phrase(), "right", 60, played, optional_notes=optional)
    assert result.correct == 1
    assert result.extra_notes == 1
    assert len(result.unmatched_played) == 1
    assert result.unmatched_played[0].pitch == 62
    # Final grading is stateless between attempts.
    assert evaluate(phrase(), "right", 60, played[:2], optional_notes=optional).clean
    view = LiveInputView()
    assert send(view, optional_notes=optional)["status"] == "heard"
    assert send(view, at=1.04, optional_notes=optional)["status"] == "unexpected"
    view.reset_attempt()
    assert send(view, optional_notes=optional)["status"] == "heard"
    view.clear_device()
    assert send(view, optional_notes=optional)["status"] == "heard"


@pytest.mark.parametrize("hand,optional,at,bpm,accepted", [
    ("right", grace(), 1.64, 60, True),
    ("right", grace(), 1.66, 60, False),
    ("right", grace(), .849, 120, True),
    ("right", grace(), .851, 120, False),
    ("right", grace(staff="left"), 1, 60, False),
    ("left", grace(), 1, 60, False),
    ("both", grace(staff="left"), 1, 60, True),
    ("right", grace(kind="note"), 1, 60, False),
])
def test_optional_acceptance_obeys_exact_pitch_hand_and_existing_window(
        hand, optional, at, bpm, accepted):
    empty = Phrase(1, 1, 2, 8, 16, ())
    result = evaluate(empty, hand, bpm, [PlayedNote(62, at, at + .02)],
                      optional_notes=(optional,))
    assert result.extra_notes == (0 if accepted else 1)
    assert not result.clean  # an ornament-only passage cannot grant mastery
    event = send(LiveInputView(), at=at, bpm=bpm, hand=hand,
                 phrase=empty, optional_notes=(optional,))
    assert event["status"] == ("heard" if accepted else "unexpected")


def test_wrong_grace_pitch_does_not_get_accepted_by_pitch_class():
    result = evaluate(phrase(), "right", 60, [PlayedNote(74, 1, 1.1)],
                      optional_notes=(grace(),))
    assert [(n.status, n.played_pitch) for n in result.notes] == [("wrong", 74)]
    assert send(LiveInputView(), pitch=74)["status"] == "unexpected"


def test_live_grace_has_own_identity_without_wrong_tether_or_required_credit():
    view = LiveInputView()
    event = send(view)
    assert (event["status"], event["source_id"], event["reference_source_id"]) == (
        "heard", "grace-1", "")
    assert not view.used
    required = send(view, pitch=60, at=1.02)
    assert (required["status"], required["source_id"]) == ("on_time", "main")
    wrong = send(view, pitch=63, at=1.03)
    assert (wrong["status"], wrong["reference_source_id"]) == ("unexpected", "main")


@pytest.mark.parametrize("overrides,status", [
    ({"at": -.2}, "count_in"),
    ({"paused": True}, "heard"),
    ({"preview": True}, "heard"),
    ({"running": False}, "heard"),
])
def test_count_in_pause_preview_do_not_consume_optional_attacks(overrides, status):
    view = LiveInputView()
    assert send(view, **overrides)["status"] == status
    event = send(view)
    assert (event["status"], event["source_id"]) == ("heard", "grace-1")


def test_seeked_live_and_settled_grace_use_phrase_relative_beats():
    source = phrase(24)
    required = source.notes[0]
    source = Phrase(2, 3, 4, 24, 32, (
        Note(24.25, 24.75, 65, 0, 0, "right", "old"), required))
    optional = (grace(), grace(id="old-grace", beat=.25, midi_pitch=67))
    view = LiveInputView()
    event = send(view, at=0, phrase=source, from_beat=1, optional_notes=optional)
    assert (event["status"], event["source_id"]) == ("heard", "grace-1")
    assert send(view, pitch=67, at=.01, phrase=source, from_beat=1,
                optional_notes=optional)["status"] == "unexpected"
    result = settled_assessment(source, "right", 60, [PlayedNote(62, 0, .1)],
        from_beat=1, until_beat=2, beats_per_bar=4, optional_notes=optional)
    assert [(n.note.source_id, n.status) for n in result.notes] == [("main", "missed")]
    result = expired_attack_misses(source, "right", 60, [PlayedNote(62, 0, .1)],
        from_beat=1, until_beat=2, optional_notes=optional)
    assert [(n.note.source_id, n.status) for n in result.notes] == [("main", "missed")]


def test_seeked_final_rebases_optional_metadata_without_mutating_source():
    from piano_teacher.optional_notes import relative_optional_notes
    optional = (grace(), grace(id="old", beat=.25))
    relative = relative_optional_notes(optional, 1)
    assert relative == (grace(beat=0),)
    assert optional[0]["beat"] == 1
    source = phrase(24)
    passage = Phrase(2, 3, 4, 25, 32, source.notes)
    result = evaluate(passage, "right", 60,
        [PlayedNote(60, 0, .5), PlayedNote(62, .03, .1)], optional_notes=relative)
    assert result.clean


def test_count_in_recording_cannot_satisfy_grace_or_required_note():
    recorder = Recorder()
    recorder.add(62, True, -.2)
    recorder.add(62, False, -.1)
    result = evaluate(phrase(), "right", 60, recorder.presses,
                      optional_notes=(grace(),))
    assert [n.status for n in result.notes] == ["missed"]
    assert result.extra_notes == 0


def test_original_evaluate_and_live_apis_keep_existing_wrong_note_behavior():
    result = evaluate(phrase(), "right", 60, [PlayedNote(62, 1, 1.1)])
    assert [(n.status, n.played_pitch) for n in result.notes] == [("wrong", 62)]
    args = dict(pitch=62, is_on=True, now=11, phrase=phrase(), hand="right",
        bpm=60, from_beat=0, run_at=10, running=True, paused=False,
        preview=False, mode="practice", transport_id=1)
    view = LiveInputView()
    view.receive(**args)
    assert view.events[-1]["status"] == "unexpected"
    result = settled_assessment(phrase(), "right", 60, [PlayedNote(62, 1, 1.1)],
        from_beat=0, until_beat=2, beats_per_bar=4)
    assert [n.status for n in result.notes] == ["wrong"]


@pytest.mark.parametrize("rolling", [False, True], ids=["fixed", "rolling"])
@pytest.mark.parametrize("mistake,expected", [
    (False, (2, 0, 2)),
    (True, (2, 1, 1)),
], ids=["grace-only", "grace-and-real-wrong"])
def test_recovery_rebases_grace_from_actual_window_and_keeps_required_misses(
        rolling, mistake, expected):
    from piano_teacher.recovery import check_rolling_two_bar_window, check_two_bar_window
    # A nonzero source phrase, a take starting at beat 2, and a later recovery
    # window all have different origins. At 120 BPM seconds are not beats.
    passage = Phrase(1, 9, 14, 32, 56, (
        Note(49, 49.5, 60, 0, 0, "right", "a"),
        Note(50, 50.5, 64, 0, 0, "right", "b"),
    ))
    optional = (grace(id="ga", anchor_id="a", beat=17, midi_pitch=62),
                grace(id="gb", anchor_id="b", beat=18, midi_pitch=65))
    played = [PlayedNote(62, 7.5, 7.6), PlayedNote(65, 8, 8.1)]
    if mistake:
        played.append(PlayedNote(61, 7.52, 7.7))
    common = dict(from_beat=2, end_beat=24, threshold=2, optional_notes=optional)
    if rolling:
        result = check_rolling_two_bar_window(passage, "right", 120, played,
            grid=(0, 4, 8, 12, 16, 20, 24), **common)
    else:
        result = check_two_bar_window(passage, "right", 120, played,
            beats_per_bar=4, **common)
    assert (result.errors, result.wrong, result.missed) == expected
    assert (result.restart_beat, result.end_beat) == (16, 24)
    assert [item["beat"] for item in optional] == [17, 18]


def guided_optional(notes=None):
    from piano_teacher.exercise_generator import ExerciseVariant
    from piano_teacher.teaching import TeachingConfig, TeachingController
    if notes is None:
        notes = (Note(16, 16.5, 60, 0, 0, "right", "main"),
                 Note(17, 17.5, 62, 0, 0, "right", "next"))
    passage = Phrase(3, 5, 6, 16, 24, notes)
    variant = ExerciseVariant("original", passage, tuple(range(len(notes))))
    # Disable ordinary stall hints for these tests: the policy is untimed and
    # a grace attack must not itself introduce a wrong-note hint.
    controller = TeachingController(TeachingConfig(stall_seconds=1000))
    controller.bind(stage_key="test", revision=1, variant=variant,
        fragment_start=0, fragment_end=8, now=10, connected=True)
    controller.start(now=10)
    return controller


def learn_send(controller, pitch=62, at=10.1, is_on=True, optional=None):
    if optional is None:
        optional = (grace(anchor_id="printed-main", anchor_source_id="main"),)
    controller.receive(pitch=pitch, is_on=is_on, at=at, optional_notes=optional)
    return controller.snapshot(now=at)


def test_learn_current_anchor_grace_is_untimed_ungraded_and_unassisted():
    controller = guided_optional()
    state = learn_send(controller, at=250,
        optional=(grace(anchor_id="printed-main", anchor_source_id="main", beat=-100),))
    assert (state["target_index"], state["target_count"]) == (0, 2)
    assert state["phase"] == "guided_wait"
    assert state["heard_pitches"] == [62]
    assert state["note_feedback"] == []
    assert not state["hint_visible"]
    assert state["assisted_count"] == 0
    assert not state["mastery_eligible"]
    learn_send(controller, at=250.1, is_on=False)
    learn_send(controller, pitch=60, at=250.2)
    state = learn_send(controller, pitch=62, at=250.3)
    assert state["completed"]
    assert state["completion"] == "unassisted"
    assert [note["status"] for note in state["note_feedback"]] == ["correct", "correct"]
    assert state["assisted_count"] == 0


def test_learn_required_pitch_wins_over_same_pitch_optional():
    controller = guided_optional()
    state = learn_send(controller, pitch=60,
        optional=(grace(midi_pitch=60, anchor_source_id="main"),))
    assert state["target_index"] == 1
    assert [(n["pitch"], n["status"]) for n in state["note_feedback"]] == [(60, "correct")]


@pytest.mark.parametrize("optional,pitch", [
    (grace(anchor_source_id="next"), 62),
    (grace(anchor_source_id="not-in-this-fragment"), 62),
    (grace(anchor_id="main"), 62),
    (grace(anchor_source_id="main"), 74),
    (grace(anchor_source_id="main", kind="note"), 62),
], ids=["future-anchor", "foreign-anchor", "printed-id-only", "wrong-octave", "not-grace"])
def test_learn_wrong_pitch_outside_current_optional_anchor_still_hints(optional, pitch):
    state = learn_send(guided_optional(), pitch=pitch, optional=(optional,))
    assert state["target_index"] == 0
    assert state["hint_visible"]
    assert state["hint_reason"] == "wrong_note"
    assert [(n["pitch"], n["status"]) for n in state["note_feedback"]] == [(pitch, "wrong")]


def test_learn_missing_source_ids_cannot_accidentally_match_missing_optional_anchor():
    controller = guided_optional((Note(16, 16.5, 60, 0, 0, "right"),))
    state = learn_send(controller, optional=(grace(),))
    assert state["hint_reason"] == "wrong_note"
    assert state["target_index"] == 0


def test_learn_held_grace_requires_release_before_later_required_pitch_credit():
    controller = guided_optional()
    learn_send(controller)
    learn_send(controller, pitch=60, at=10.2)
    state = learn_send(controller, at=10.3)
    assert state["target_index"] == 1  # duplicate note-on is still the held grace
    learn_send(controller, at=10.05, is_on=False)  # stale release cannot clear it
    state = learn_send(controller, at=10.35)
    assert state["target_index"] == 1
    learn_send(controller, at=10.4, is_on=False)
    state = learn_send(controller, at=10.5)
    assert state["completed"]
    assert state["completion"] == "unassisted"


def test_learn_grace_anchored_to_any_current_chord_member_never_joins_required_chord():
    controller = guided_optional((
        Note(16, 17, 60, 0, 0, "right", "main"),
        Note(16, 17, 64, 0, 0, "right", "chord-e"),
    ))
    learn_send(controller, pitch=60)
    state = learn_send(controller, at=10.15,
        optional=(grace(anchor_source_id="chord-e"),))
    assert state["target_index"] == 0
    assert state["note_feedback"] == []
    state = learn_send(controller, pitch=64, at=10.2)
    assert state["completed"]
    assert state["completion"] == "unassisted"
    assert [n["status"] for n in state["note_feedback"]] == ["correct", "correct"]

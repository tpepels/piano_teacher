"""Grading evidence retains the exact assignment and independent measurements."""
from dataclasses import FrozenInstanceError, asdict

import pytest

from piano_teacher.exercise_contracts import TempoMap, TempoSegment
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import NoteAssessment, PlayedNote, Recorder, evaluate
from piano_teacher.timed_assessment import assess_timed_window


def _phrase(*notes, start=0, end=4):
    return Phrase(1, 1, 1, start, end, tuple(notes))


def _observation(entry):
    observation = getattr(entry, "observation", None)
    assert observation is not None, "The authoritative grading pass must retain its observation"
    return observation


def test_nearest_repeated_pitch_retains_original_played_indices():
    phrase = _phrase(Note(0, .5, 60, 0, 0), Note(.25, .75, 60, 0, 0))
    played = [PlayedNote(60, .25, .75), PlayedNote(60, 0, .5)]

    result = evaluate(phrase, "right", 60, played)

    assert result.clean
    assert [_observation(entry).played_index for entry in result.notes] == [1, 0]
    assert [_observation(entry).actual_onset for entry in result.notes] == [0, .25]


def test_omitted_repeated_pitch_does_not_invent_a_match_for_earlier_note():
    phrase = _phrase(Note(0, .25, 60, 0, 0), Note(.25, .5, 60, 0, 0))

    result = evaluate(phrase, "right", 60, [PlayedNote(60, .25, .5)])

    assert [entry.status for entry in result.notes] == ["missed", "correct"]
    assert [_observation(entry).played_index for entry in result.notes] == [None, 0]


def test_chord_wrong_pitch_assignment_keeps_exact_pitch_reservation_and_hold_fact():
    phrase = _phrase(*(Note(0, 1, pitch, 0, 0) for pitch in (60, 64, 67)))
    played = [PlayedNote(64, .01, 1.01), PlayedNote(61, -.02, .08),
              PlayedNote(68, .03, 1.03)]

    result = evaluate(phrase, "right", 60, played)

    assert [entry.status for entry in result.notes] == ["wrong", "correct", "wrong"]
    assert result.extra_notes == 0
    assert [_observation(entry).played_index for entry in result.notes] == [1, 0, 2]
    wrong = _observation(result.notes[0])
    assert result.notes[0].played_pitch == wrong.actual_pitch == 61
    assert wrong.actual_onset == -.02 and wrong.actual_release == .08
    assert wrong.pitch_error is True
    assert wrong.timing_error is None and wrong.hold_error == "short"
    assert wrong.onset_residual == pytest.approx(-.02)
    assert wrong.release_residual == pytest.approx(-.92)
    assert wrong.duration_residual == pytest.approx(-.9)


def test_late_and_short_measurements_coexist_without_changing_priority_or_acceptance():
    phrase = _phrase(*(Note(2 * index, 2 * index + 1, 60 + index, 0, 0)
                       for index in range(4)), end=8)
    played = [PlayedNote(60, .2, .25), PlayedNote(61, 1, 1.5),
              PlayedNote(62, 2, 2.5), PlayedNote(63, 3, 3.5)]

    result = evaluate(phrase, "right", 120, played)

    assert [entry.status for entry in result.notes] == ["late", "correct", "correct", "correct"]
    assert result.passed and not result.clean
    assert (result.total_attacks, result.yellow_attacks) == (4, 1)
    observation = _observation(result.notes[0])
    assert observation.pitch_error is False
    assert observation.timing_error == "late" and observation.hold_error == "short"
    assert observation.onset_residual == pytest.approx(.2)
    assert observation.release_residual == pytest.approx(-.25)
    assert observation.duration_residual == pytest.approx(-.45)


@pytest.mark.parametrize("onset,status,timing_error", [(0, "short", None), (.2, "late", "late")])
def test_unreleased_has_no_fabricated_duration_or_measured_short_flag(onset, status, timing_error):
    phrase = _phrase(Note(0, 2, 60, 0, 0))

    entry = evaluate(phrase, "right", 120, [PlayedNote(60, onset, None)]).notes[0]

    assert entry.status == status
    observation = _observation(entry)
    assert observation.unreleased is True
    assert observation.actual_release is None
    assert observation.release_residual is None and observation.duration_residual is None
    assert observation.hold_error is None and observation.timing_error == timing_error
    assert observation.onset_residual == onset


def test_missed_retains_clipped_expected_timing_and_explicit_missing_actuals():
    phrase = _phrase(Note(4, 7, 60, 0, 0), start=4, end=6)

    entry = evaluate(phrase, "right", 120, []).notes[0]

    assert entry.status == "missed"
    observation = _observation(entry)
    assert observation.expected_onset == 0 and observation.expected_release == 1
    assert observation.local_seconds_per_beat == .5
    assert observation.onset_tolerance == .13 and observation.duration_tolerance == .5
    assert observation.played_index is None and observation.press_id is None
    assert observation.actual_pitch is None
    assert observation.actual_onset is None and observation.actual_release is None
    assert observation.onset_residual is None
    assert observation.release_residual is None and observation.duration_residual is None
    assert observation.unreleased is False and observation.ambiguous_pairing is False
    assert observation.pitch_error is False
    assert observation.timing_error is None and observation.hold_error is None


def test_tempo_mapped_observations_keep_cross_segment_seconds_and_local_tolerances():
    phrase = _phrase(Note(9, 11, 60, 0, 0), Note(10, 12, 62, 0, 0), start=8, end=12)
    tempo = TempoMap("mapped", (TempoSegment(0, 2, 120), TempoSegment(2, 4, 60)))

    result = assess_timed_window(phrase, "right", tempo,
                                [PlayedNote(60, .1, 1.6), PlayedNote(62, .75, 1)],
                                from_beat=1)

    assert [entry.status for entry in result.notes] == ["correct", "late"]
    first, second = [_observation(entry) for entry in result.notes]
    assert (first.expected_onset, first.expected_release, first.local_seconds_per_beat) == (0, 1.5, .5)
    assert (second.expected_onset, second.expected_release, second.local_seconds_per_beat) == (.5, 2.5, 1)
    assert (first.onset_tolerance, first.duration_tolerance) == (.13, .75)
    assert second.onset_tolerance == .2 and second.duration_tolerance == pytest.approx(1.28)
    assert first.onset_residual == pytest.approx(.1)
    assert first.release_residual == pytest.approx(.1)
    assert first.duration_residual == pytest.approx(0)
    assert second.onset_residual == .25 and second.release_residual == -1.5
    assert second.duration_residual == -1.75 and second.hold_error == "short"


def test_wrong_pitch_uses_the_same_single_expected_timing_resolution():
    note = Note(0, 2, 60, 0, 0)
    calls = []

    def expected_seconds(actual_note):
        calls.append(actual_note)
        return 1., 2., .5

    entry = evaluate(_phrase(note), "right", 120, [PlayedNote(61, 1.1, 1.2)],
                     expected_seconds=expected_seconds).notes[0]

    assert entry.status == "wrong"
    observation = _observation(entry)
    assert calls == [note]
    assert observation.expected_onset == 1 and observation.expected_release == 2
    assert observation.played_index == 0 and observation.actual_pitch == 61
    assert observation.onset_residual == pytest.approx(.1)
    assert observation.hold_error == "short"


def test_recorder_marks_overlapping_fifo_pairing_without_changing_release_assignment():
    recorder = Recorder()
    for pitch, down, seconds in [(60, True, 0), (60, True, .25),
                                 (60, False, .5), (60, False, .75),
                                 (62, True, 1), (62, False, 1.5)]:
        recorder.add(pitch, down, seconds)
    phrase = _phrase(Note(0, .5, 60, 0, 0), Note(.25, .75, 60, 0, 0),
                     Note(1, 1.5, 62, 0, 0))

    result = evaluate(phrase, "right", 60, recorder.presses)

    assert result.clean
    assert [(press.onset, press.release) for press in recorder.presses] == [(0, .5), (.25, .75), (1, 1.5)]
    assert [_observation(entry).ambiguous_pairing for entry in result.notes] == [True, True, False]
    assert [_observation(entry).press_id for entry in result.notes] == [0, 1, 2]


def test_bounded_mapped_window_retains_recorder_identity_after_filtering():
    recorder = Recorder()
    for pitch, down, seconds in [(60, True, 0), (60, False, .5),
                                 (62, True, 1), (62, False, 2)]:
        recorder.add(pitch, down, seconds)
    phrase = _phrase(Note(8, 9, 60, 0, 0), Note(10, 11, 62, 0, 0), start=8, end=12)
    tempo = TempoMap("mapped", (TempoSegment(0, 2, 120), TempoSegment(2, 4, 60)))

    result = assess_timed_window(phrase, "right", tempo, recorder.presses,
                                start_beat=2, end_beat=3)

    assert result.clean
    observation = _observation(result.notes[0])
    assert observation.played_index == 0 and observation.press_id == 1
    assert observation.actual_pitch == 62
    assert observation.actual_onset == observation.expected_onset == 1
    assert observation.actual_release == observation.expected_release == 2


def test_observation_serializes_as_frozen_scalar_facts_without_changing_legacy_constructor():
    note = Note(0, 2, 60, 0, 0)
    entry = evaluate(_phrase(note), "right", 120, [PlayedNote(60, 0, 1)]).notes[0]
    observation = _observation(entry)

    payload = asdict(entry)["observation"]
    assert payload == {
        "played_index": 0, "press_id": None,
        "expected_onset": 0, "expected_release": 1,
        "actual_pitch": 60, "actual_onset": 0, "actual_release": 1,
        "local_seconds_per_beat": .5, "onset_tolerance": .13,
        "duration_tolerance": .5, "onset_residual": 0,
        "release_residual": 0, "duration_residual": 0,
        "pitch_error": False, "timing_error": None, "hold_error": None,
        "unreleased": False, "ambiguous_pairing": False,
    }
    with pytest.raises(FrozenInstanceError):
        observation.actual_pitch = 61
    assert NoteAssessment(note, "wrong", 61).observation is None


@pytest.mark.parametrize("played,status,passed", [
    ([PlayedNote(60, 0, 1)], "correct", True),
    ([PlayedNote(60, -.2, .8)], "early", False),
    ([PlayedNote(60, .2, 1.2)], "late", False),
    ([PlayedNote(60, 0, .1)], "short", False),
    ([PlayedNote(60, 0, 2)], "long", False),
    ([], "missed", False),
    ([PlayedNote(61, .1, 1.1)], "wrong", False),
])
def test_observations_preserve_existing_status_and_accepted_take_rule(played, status, passed):
    result = evaluate(_phrase(Note(0, 2, 60, 0, 0)), "right", 120, played)

    assert result.notes[0].status == status
    assert result.passed is passed
    assert _observation(result.notes[0]) is not None

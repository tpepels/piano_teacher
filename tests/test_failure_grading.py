"""How each kind of mistake is graded, and what follows it.

The window is bar 1 of the right hand: a three-note chord on beat 0 and
one note on beat 3, at the 40 BPM opening tempo. The onset tolerance there
is one sixteenth (375 ms), larger than the 150 ms floor. Each case plays a
real take on the engine's clock and checks three things a learner sees:
every note's final colour/status, the counts kept in the learning history,
and the next step (owner request 2026-11-24: test failures well).
"""
import pytest

from test_midi_journeys import tempo

CHORD, LAST = (0, 1, 2), 3   # note indexes in score.semantic order


def play(session, state, *, wrong=(), missing=(), extra=(), shift=None,
         held=.9, speed=1.0, doubled=()):
    """Play the running take. `shift` = (note index, seconds) moves one
    attack; `held` is the fraction of each note's length that is held;
    `speed` > 1 rushes the whole take; `doubled` notes are struck twice."""
    start = state["playback_timeline"]["current"]["deadline_ms"]/1000
    source = session.ask("score.semantic")
    floor, seconds_per_beat = state["play_from_beat"], 60/state["bpm"]
    events = []
    for index, note in enumerate(source["notes"]):
        if index in missing:
            continue
        at = start+(note["onset_beats"]-floor)*seconds_per_beat/speed
        if shift is not None and index == shift[0]:
            at += shift[1]
        pitch = note["midi_pitch"]+(1 if index in wrong else 0)
        events += [(at, True, pitch),
                   (at+note["duration_beats"]*seconds_per_beat*held/speed, False, pitch)]
        if index in doubled:
            events += [(at+.1, True, pitch), (at+.15, False, pitch)]
    for after, pitch in extra:
        events += [(start+after, True, pitch), (start+after+.05, False, pitch)]
    for at, on, pitch in sorted(events):
        session.clock.at = max(session.clock.at, at)
        session.engine.midi.port.send(pitch, on)
    sounding = source["practice_timeline"]["sounding_duration_beats"]
    session.clock.at = max(session.clock.at, start+(sounding-floor)*seconds_per_beat+.001)
    for _ in range(5):
        session.tick(.02)
    return session.snapshot()


def graded(session, transport):
    """Final per-note statuses of one take, in score order."""
    return [event["status"] for event in session.ask("feedback.events")["events"]
            if event.get("final") and event.get("transport_id") == transport]


def counts(session):
    pitch = session.ask("learning.statistics", scope="full")["pitch"]
    return {key: pitch[key] for key in ("correct_required_pitches", "wrong", "omitted", "extra")}


C, M, W = "correct", "missed", "wrong"
CASES = {
    # name: (play options, final statuses, (correct, wrong, omitted, extra))
    "one chord note missing": ({"missing": (1,)}, [C, M, C, C], (3, 0, 1, 0)),
    "two chord notes missing": ({"missing": (1, 2)}, [C, M, M, C], (2, 0, 2, 0)),
    "whole chord missing": ({"missing": CHORD}, [M, M, M, C], (1, 0, 3, 0)),
    "last note missing": ({"missing": (LAST,)}, [C, C, C, M], (3, 0, 1, 0)),
    "nothing played": ({"missing": CHORD+(LAST,)}, [M, M, M, M], (0, 0, 4, 0)),
    "only random keys": ({"missing": CHORD+(LAST,), "extra": ((.5, 61), (2, 65), (4, 70))},
                         [M, M, M, M], (0, 0, 4, 3)),
    "one wrong pitch in the chord": ({"wrong": (0,)}, [W, C, C, C], (3, 1, 0, 0)),
    "every pitch wrong": ({"wrong": CHORD+(LAST,)}, [W, W, W, W], (0, 4, 0, 0)),
    "one extra key": ({"extra": ((.05, 60),)}, [C, C, C, C], (4, 0, 0, 1)),
    "a note struck twice": ({"doubled": (LAST,)}, [C, C, C, C], (4, 0, 0, 1)),
    "a wrong key then the right one": ({"extra": ((4.45, 80),)}, [C, C, C, C], (4, 0, 0, 1)),
    "last note just too late": ({"shift": (LAST, .6)}, [C, C, C, M], (3, 0, 1, 0)),
    "last note just too early": ({"shift": (LAST, -.6)}, [C, C, C, "early"], (4, 0, 0, 0)),
    "last note far too late": ({"shift": (LAST, 3.0)}, [C, C, C, M], (3, 0, 1, 0)),
    "last note far too early": ({"shift": (LAST, -3.0)}, [C, C, C, M], (3, 0, 1, 1)),
    "first chord far too late": ({"shift": (0, 3.0)}, [M, C, C, C], (3, 0, 1, 1)),
    # A press in the count-in close enough to be matched to the first note
    # is graded (early); one far into the count-in is not part of the take.
    "first chord note far too early": ({"shift": (0, -2.0)}, [M, C, C, C], (3, 0, 1, 0)),
    "first chord note just too early": ({"shift": (0, -.45)}, ["early", C, C, C], (4, 0, 0, 0)),
    "first chord note just too late": ({"shift": (0, .45)}, [M, C, C, C], (3, 0, 1, 1)),
    "the whole take rushed twice as fast": ({"speed": 2.0}, [C, C, C, M], (3, 0, 1, 1)),
}


@pytest.mark.parametrize("name", list(CASES))
def test_a_mistake_fails_the_take_and_the_same_tempo_follows(practice_session, name):
    options, statuses, (correct, wrong, omitted, extra) = CASES[name]
    session = practice_session(bars=2, chords=True)
    state = tempo(session)
    session.ask("score.native_layout")
    after = play(session, state, **options)
    assert graded(session, state["transport_id"]) == statuses
    assert counts(session) == {"correct_required_pitches": correct, "wrong": wrong,
                               "omitted": omitted, "extra": extra}
    # One failed take: the same window again at the same tempo, no credit.
    assert after["running"] and after["transport_id"] == state["transport_id"]+1
    assert after["bpm"] == 40 and after["streak"] == 0
    assert after["flow"]["message_kind"] == "again"
    assert after["lesson_steps_mastered"] == 0
    assessments = session.ask("learning.statistics", scope="full")["assessments"]
    assert (assessments["accepted"], assessments["rejected"]) == (0, 1)


@pytest.mark.parametrize("shift", [-.1, .1], ids=["early", "late"])
def test_an_attack_inside_the_tolerance_stays_correct(practice_session, shift):
    session = practice_session(bars=2, chords=True)
    state = tempo(session)
    session.ask("score.native_layout")
    after = play(session, state, shift=(LAST, shift))
    assert graded(session, state["transport_id"]) == [C, C, C, C]
    assert 40 < after["bpm"] < 80   # clean, but off centre: a smaller step


@pytest.mark.parametrize("hold_grading,statuses,clean", [
    (False, [C, C, C, C], True), (True, ["short"]*4, False)],
    ids=["holds-not-graded", "holds-graded"])
def test_notes_released_far_too_soon_fail_only_when_holds_are_graded(
        practice_session, hold_grading, statuses, clean):
    session = practice_session(bars=2, chords=True)
    session.ask("settings.update", grade_note_holds=hold_grading)
    state = tempo(session)
    session.ask("score.native_layout")
    after = play(session, state, held=.1)
    assert graded(session, state["transport_id"]) == statuses
    assert (after["bpm"] > 40) is clean


@pytest.mark.parametrize("first,second", [
    ({"missing": (1,)}, {"wrong": (0,)}),
    ({"shift": (LAST, .6)}, {"shift": (LAST, -.6)}),
    ({"extra": ((.05, 60),)}, {"missing": CHORD+(LAST,)}),
], ids=["missing-then-wrong", "late-then-early", "extra-then-nothing"])
def test_any_two_failures_in_a_row_at_the_floor_return_to_free(practice_session, first, second):
    session = practice_session(bars=2, chords=True)
    state = tempo(session)
    again = play(session, state, **first)
    assert again["running"] and again["bpm"] == 40
    free = play(session, again, **second)
    assert (free["mode"], free["flow"]["step"]) == ("learn", "free")
    assert not free["running"] and free["lesson_steps_mastered"] == 0


def test_two_failures_above_the_floor_slow_down_and_a_clean_take_resets_the_count(practice_session):
    session = practice_session(bars=2, chords=True)
    state = tempo(session)
    state = play(session, state)                       # clean: up to the target
    assert state["bpm"] == 80
    state = play(session, state, missing=(LAST,))      # one failure: same tempo
    assert state["bpm"] == 80
    state = play(session, state)                       # clean again: counter reset
    assert state["bpm"] == 80 and state["streak"] == 1
    state = play(session, state, wrong=(0,))           # failure 1 of 2, streak lost
    assert state["bpm"] == 80 and state["streak"] == 0
    state = play(session, state, shift=(LAST, .6))     # failure 2 of 2: slower
    assert state["bpm"] == 72 and state["flow"]["message_kind"] == "slower"


WINDOWS = {
    # name: (fixture options, window to select or None for the opening one)
    "right hand, one bar": ({}, None),
    "left hand, one bar": ({}, (1, 1, "left")),
    "both hands, one bar": ({}, (1, 1, "both")),
    "right hand, two bars": ({}, (1, 2, "right")),
    "MusicXML, right hand": ({"musicxml": True}, None),
}
MISTAKES = {
    # name: (play options built from the window's note count, index, status)
    "first note missing": (lambda n: {"missing": (0,)}, 0, M),
    "last note missing": (lambda n: {"missing": (n-1,)}, -1, M),
    "first note wrong": (lambda n: {"wrong": (0,)}, 0, W),
    "last note too late": (lambda n: {"shift": (n-1, .6)}, -1, M),
    "first note too early": (lambda n: {"shift": (0, -.45)}, 0, "early"),
}


def window_take(session, window):
    if window is not None:
        first, last, hand = window
        session.select(first, last, hand=hand)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    expected_bpm = 80 if window == (1, 1, "left") else 40
    assert state["running"] and state["bpm"] == expected_bpm, state
    session.ask("score.native_layout")
    return state


@pytest.mark.parametrize("window", list(WINDOWS))
@pytest.mark.parametrize("mistake", list(MISTAKES))
def test_every_window_kind_grades_a_mistake_and_repeats(practice_session, window, mistake):
    options, selected = WINDOWS[window]
    session = practice_session(bars=3, chords=True, **options)
    state = window_take(session, selected)
    notes = session.ask("score.semantic")["notes"]
    build, index, status = MISTAKES[mistake]
    after = play(session, state, **build(len(notes)))
    expected = [C]*len(notes)
    expected[index] = status
    assert graded(session, state["transport_id"]) == expected
    assert after["running"] and after["bpm"] == state["bpm"]
    assert after["flow"]["message_kind"] == "again"
    assert after["hand"] == state["hand"]
    assert (after["first_bar"], after["last_bar"]) == (state["first_bar"], state["last_bar"])


@pytest.mark.parametrize("window", list(WINDOWS))
def test_every_window_kind_passes_a_clean_take_and_rejects_silence(practice_session, window):
    options, selected = WINDOWS[window]
    session = practice_session(bars=3, chords=True, **options)
    state = window_take(session, selected)
    count = len(session.ask("score.semantic")["notes"])
    clean = play(session, state)
    assert graded(session, state["transport_id"]) == [C]*count
    if state["bpm"] == state["target_bpm"]:
        assert clean["bpm"] == state["bpm"] and clean["streak"] == 1
    else:
        assert clean["bpm"] > state["bpm"]
    silent = play(session, clean, missing=tuple(range(count)))
    assert graded(session, clean["transport_id"]) == [M]*count
    assert silent["bpm"] == clean["bpm"] and silent["flow"]["message_kind"] == "again"

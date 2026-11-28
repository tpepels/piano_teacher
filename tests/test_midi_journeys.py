"""Whole practice journeys driven by real MIDI keys, correct and incorrect.

Every take is played on the engine's own clock from the real score
(the score bundle), as a learner at the piano would; only the inputs vary.
The expected states are the Practice Flow rules (docs/practice-flow.md);
owner request 2026-11-24: more MIDI journeys, including wrong notes.
"""
import random

import pytest


def play(session, state, *, wrong=(), missing=(), extra=(), late=None):
    """Play the running take: note indexes in `wrong` a semitone off, those
    in `missing` silent, `extra` (seconds after the downbeat, pitch) keys
    added, and the first attack `late` seconds late. Returns the state
    after the take has finished and the engine has continued."""
    current = state["playback_timeline"]["current"]
    start = current["deadline_ms"]/1000
    source = session.ask("score.bundle")["model"]
    floor, seconds_per_beat = state["play_from_beat"], 60/state["bpm"]
    events = []
    for index, note in enumerate(source["notes"]):
        if index in missing:
            continue
        at = start+(note["onset_beats"]-floor)*seconds_per_beat
        if late is not None and index == 0:
            at += late
        pitch = note["midi_pitch"]+(1 if index in wrong else 0)
        events += [(at, True, pitch),
                   (at+note["duration_beats"]*seconds_per_beat*.9, False, pitch)]
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


def tempo(session):
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert state["mode"] == "practice" and state["running"], state
    assert state["flow"]["step"] == "tempo"
    assert 40 <= state["bpm"] <= 80
    return state


def next_take(before, after):
    assert after["running"] and after["transport_id"] == before["transport_id"]+1, after
    return after


def test_wrong_note_repeats_and_a_second_failure_at_the_floor_returns_to_free(practice_session):
    session = practice_session(bars=2, chords=True)
    first = tempo(session)
    assert first["bpm"] == 40
    again = next_take(first, play(session, first, wrong=(0,1)))
    assert again["bpm"] == 40 and again["flow"]["message_kind"] == "again"
    assert again["take_result"] is None or not again["take_result"]["clean"]
    free = play(session, again, wrong=(0,1))
    assert free["mode"] == "learn" and free["flow"]["step"] == "free"
    assert not free["running"] and free["lesson_steps_mastered"] == 0
    # Free asks for the complete window again before Tempo restarts at 50%.
    session.finish_free()
    restarted = session.ready_score()
    assert restarted["running"] and restarted["bpm"] == 40
    assert restarted["flow"]["step"] == "tempo"


def test_missing_note_and_extra_key_fail_and_two_failures_above_the_floor_slow_down(practice_session):
    session = practice_session(bars=2, chords=True)
    first = tempo(session)
    faster = next_take(first, play(session, first))
    assert faster["bpm"] == 80 and faster["flow"]["message_kind"] == "faster"
    missing = next_take(faster, play(session, faster, missing=(1,2)))
    assert missing["bpm"] == 80 and missing["streak"] == 0
    slower = next_take(missing, play(session, missing, missing=(1,2), extra=((.05, 60),)))
    # 10% of the 80 BPM target, never below 50%.
    assert slower["bpm"] == 72 and slower["flow"]["message_kind"] == "slower"
    assert slower["lesson_steps_mastered"] == 0


@pytest.mark.parametrize("late,clean", [(.1, True), (.6, False)],
                         ids=["within-tolerance", "outside-tolerance"])
def test_a_late_attack_is_graded_against_the_onset_tolerance(practice_session, late, clean):
    # Tolerance: the larger of 150 ms and one sixteenth at the local tempo
    # (at 40 BPM a sixteenth is 375 ms).
    session = practice_session(bars=2, chords=True)
    first = tempo(session)
    after = next_take(first, play(session, first, late=late))
    assert (after["bpm"] > 40) is clean
    if clean:
        assert 40 < after["bpm"] < 80
        assert after["flow"]["message_kind"] == "faster"
    else:
        assert after["flow"]["message_kind"] == "again"


def test_two_clean_takes_at_target_master_the_window_and_move_to_the_left_hand(practice_session):
    session = practice_session(bars=2)
    state = tempo(session)
    assert state["bpm"] == 80
    state = next_take(state, play(session, state))
    assert state["streak"] == 1 and state["lesson_steps_mastered"] == 0
    done = play(session, state)
    assert done["lesson_steps_mastered"] == 1
    assert (done["mode"], done["hand"], done["flow"]["step"]) == ("listen", "left", "listen")
    assert (done["first_bar"], done["last_bar"]) == (1, 1)


def test_a_failed_take_breaks_the_clean_streak_at_target(practice_session):
    session = practice_session(bars=2)
    state = tempo(session)
    assert state["bpm"] == 80
    state = next_take(state, play(session, state))
    assert state["streak"] == 1
    state = next_take(state, play(session, state, wrong=(1,)))
    assert state["streak"] == 0 and state["lesson_steps_mastered"] == 0
    state = next_take(state, play(session, state))
    assert state["streak"] == 1 and state["lesson_steps_mastered"] == 0


def test_wrong_key_in_free_shows_the_hint_and_waits_for_the_right_key(practice_session):
    session = practice_session(bars=2)
    session.finish_listen()
    state = session.reach_free_target()
    targets = state["teaching"]["expected_notes"]
    session.strike(targets[0]["pitch"]+1)
    wrong = session.tick()
    assert wrong["teaching"]["hint_reason"] == "wrong_note"
    assert wrong["teaching"]["target_index"] == 0
    assert session.tick(30)["teaching"]["target_index"] == 0
    session.strike(targets[0]["pitch"])
    assert session.tick(.1)["teaching"]["target_index"] == 1


def test_a_take_godot_could_not_draw_is_placed_again_once(practice_session):
    session = practice_session(bars=2)
    state = tempo(session)
    take = state["playback_timeline"]["current"]
    session.ask("playback.failure", take_id=take["take_id"], segment_id=take["segment_id"],
                reason="timeline_take_not_drawn")
    again = session.snapshot()
    assert again["running"] and again["playback_timeline"]["state"] != "failed"
    second = again["playback_timeline"]["current"]
    assert second["take_id"] != take["take_id"]
    assert second["deadline_ms"]/1000 > session.clock()
    # The same failure again at once is a real display problem: stop and say so.
    session.ask("playback.failure", take_id=second["take_id"], segment_id=second["segment_id"],
                reason="timeline_take_not_drawn")
    stopped = session.snapshot()
    assert not stopped["running"] and stopped["playback_timeline"]["state"] == "failed"
    assert stopped["playback_timeline"]["failure"] == "The score stopped displaying correctly"


@pytest.mark.parametrize("seed", range(6))
def test_long_seeded_journeys_never_fail_or_jam(practice_session, seed):
    """Random correct and incorrect takes, Pause anywhere, Retry, Stop and
    Listen again: the session never fails, raises or stops progressing."""
    rng = random.Random(seed)
    session = practice_session(bars=3)
    state = tempo(session)
    transport = state["transport_id"]
    for _ in range(30):
        state = session.snapshot()
        assert state["playback_timeline"]["state"] != "failed", state["playback_timeline"]
        assert state["transport_id"] >= transport
        transport = state["transport_id"]
        if state["mode"] == "learn":
            session.finish_free()
            session.ready_score()
            continue
        if state["mode"] == "listen":
            session.finish_listen()
            continue
        if state["flow"]["step"] == "section_choice":
            session.command("section_next")
            continue
        if not state["running"]:
            state = session.ready_score()
            if not state["running"]:
                session.command(state["controls"]["primary"]["action"])
                state = session.ready_score()
            assert state["running"], (state["feedback"], state["controls"]["primary"])
        action = rng.choice(["clean", "clean", "wrong", "missing", "extra", "late",
                             "pause_playing", "pause_count_in", "retry", "stop", "listen"])
        if action == "stop":
            assert not session.command("ui_stop")["running"]
        elif action == "listen":
            session.command("listen")
        elif action in ("pause_playing", "pause_count_in", "retry"):
            if action == "pause_playing":
                session.clock.at = max(session.clock.at,
                    state["playback_timeline"]["current"]["deadline_ms"]/1000+.3)
                session.tick()
            if action == "retry":
                session.command("restart")
            else:
                session.command("pause")
                session.tick(rng.uniform(1, 200))
                session.command("resume")
            resumed = session.snapshot()
            assert resumed["running"] and not resumed["paused"], resumed["feedback"]
            play(session, resumed)
        else:
            play(session, state, **{
                "clean": {}, "wrong": {"wrong": (0,)}, "missing": {"missing": (0,)},
                "extra": {"extra": ((.05, 60),)}, "late": {"late": .6}}[action])


def test_unpresented_segment_cannot_grade_or_advance(practice_session):
    session = practice_session(bars=2)
    state = tempo(session)
    take = state["playback_timeline"]["current"]
    session.engine.playback.require_presentation = True
    session.clock.at = take["deadline_ms"]/1000 + .1
    session.strike(72)
    held = session.tick(30)
    assert held["transport_id"] == state["transport_id"]
    assert held["lesson_steps_mastered"] == state["lesson_steps_mastered"]
    assert not held["playback_timeline"]["presentation_confirmed"]
    assert not session.engine.take.recorder.presses
    late = session.ask("state.snapshot", placement_revision=state["revision"],
                       presented_segment=take["segment_id"])
    assert not late["playback_timeline"]["presentation_confirmed"]
    session.ask("playback.failure", take_id=take["take_id"],
                segment_id=take["segment_id"], reason="timeline_take_not_drawn")
    replacement = session.snapshot()
    next_take = replacement["playback_timeline"]["current"]
    assert next_take["segment_id"] != take["segment_id"]
    stale = session.ask("state.snapshot", placement_revision=replacement["revision"],
                        presented_segment=take["segment_id"])
    assert not stale["playback_timeline"]["presentation_confirmed"]
    wrong_revision = session.ask("state.snapshot", placement_revision=replacement["revision"]-1,
                                 presented_segment=next_take["segment_id"])
    assert not wrong_revision["playback_timeline"]["presentation_confirmed"]
    confirmed = session.ask("state.snapshot", placement_revision=replacement["revision"],
                            presented_segment=next_take["segment_id"])
    assert confirmed["playback_timeline"]["presentation_confirmed"]
    session.command("stop")
    after = session.ask("state.snapshot", placement_revision=replacement["revision"],
                        presented_segment=next_take["segment_id"])
    assert not after["running"]


def test_unpresented_native_take_expires_without_automatic_retries(practice_session):
    session = practice_session(bars=2)
    state = tempo(session)
    take = state["playback_timeline"]["current"]
    session.engine.playback.require_presentation = True
    session.clock.at = take["deadline_ms"]/1000 + 121
    expired = session.tick()
    assert not expired["running"]
    assert expired["playback_timeline"]["state"] == "failed"
    assert expired["lesson_steps_mastered"] == state["lesson_steps_mastered"]
    for _ in range(3):
        after = session.tick(1)
        assert not after["running"]
        assert after["playback_timeline"]["state"] == "failed"

"""Player-visible state journeys through the production engine and fake MIDI port.

Fake time and MIDI input are test stimuli only: the engine owns all lesson,
transport, grading, feedback and persistence decisions. No simulated state
machine or replacement evaluator is involved.
"""
from session_inputs import take
import json

import pytest

from piano_teacher.inprocess import INVALID


def state_at(session, *, step=None, mode=None, hand=None, bpm=None,
             running=None, paused=None):
    state = session.snapshot()
    if step is not None:
        assert state["flow"]["step"] == step, state
    if mode is not None:
        assert state["mode"] == mode, state
    if hand is not None:
        assert state["hand"] == hand, state
    if bpm is not None:
        assert state["bpm"] == bpm, state
    if running is not None:
        assert state["running"] is running, state
    if paused is not None:
        assert state["paused"] is paused, state
    return state


def emit_at_beats(session, start, bpm, events):
    """Drive the connected test port exactly like real MIDI note on/off."""
    for offset, on, pitch in sorted(events):
        session.clock.at = start + offset * 60 / bpm
        session.engine.midi.port.send(pitch, on)


def failed_take(session, *, fault="missed"):
    session.ready_score()
    state = state_at(session, step="tempo", mode="practice", running=True)
    source = session.ask("score.semantic")
    assert take(state)["transport_id"] == state["transport_id"]
    start = take(state)["deadline_ms"] / 1000
    bpm = state["bpm"]
    floor = state["play_from_beat"]
    notes = source["notes"]
    before_inputs = state["midi_input_count"]
    if fault != "missed":
        events = []
        for index, note in enumerate(notes):
            onset = float(note["onset_beats"]) - floor
            release = onset + float(note["duration_beats"])
            pitch = int(note["midi_pitch"])
            if fault == "wrong" and index == 0:
                pitch = 61  # Real note-on, but absent from the selected score.
            if fault == "late" and index == 0:
                onset += .8 * bpm / 60  # 800 ms beyond permitted timing slack.
                release += .8 * bpm / 60
            events.extend([(onset, True, pitch), (release, False, pitch)])
        if fault == "extra":
            events += [(1.25, True, 61), (1.32, False, 61)]
        emit_at_beats(session, start, bpm, events)
    before_transport = state["transport_id"]
    result = session.play_take(correct=False)
    events = session.ask("feedback.events")["events"]
    assert result["mastered"] == 0 and result["flow"]["step"] in ("tempo","free")
    assert result["bpm"] == bpm or result["flow"]["step"] == "free"
    after_inputs = session.snapshot()["midi_input_count"]
    if fault == "missed":
        assert after_inputs == before_inputs  # No simulated presses at all.
    else:
        assert after_inputs > before_inputs  # Production MIDI callback was hit.
    return result, events


def climb_to_mastery(session, hand, index):
    """Play clean takes until the step is mastered: Tempo starts at 50%,
    only rises, and ends with exactly two clean takes at target."""
    climbed = []
    while not session.ask("lesson.overview")["steps"][index]["completed"]:
        state = session.snapshot()
        state_at(session, step="tempo", hand=hand, bpm=state["bpm"], running=True)
        climbed.append(state["bpm"])
        session.play_take()
        assert len(climbed) <= 12
    assert climbed[0] == 40 and climbed == sorted(climbed)
    assert climbed[-2:] == [80, 80] and climbed.count(80) == 2
    return climbed


def test_fake_keyboard_traverses_the_complete_hand_and_final_mastery_graph(practice_session):
    session = practice_session(bars=1)
    state_at(session, step="listen", mode="listen", hand="right")
    visited = []
    for hand in ("right", "left", "both"):
        if session.snapshot()["flow"]["step"] == "listen":
            session.finish_listen()
        state_at(session, step="free", mode="learn", hand=hand, running=False)
        session.finish_free()
        session.ready_score()
        state_at(session, step="tempo", mode="practice", hand=hand, bpm=40, running=True)
        # 50%, then faster after each precisely timed clean take, then two
        # clean target takes. Every attack and release is sent through the
        # test's real MIDI callback.
        index = {"right": 0, "left": 1, "both": 2}[hand]
        climbed = climb_to_mastery(session, hand, index)
        visited.extend((hand, bpm) for bpm in climbed)
        assert session.snapshot()["mastered"] == {"right":1,"left":2,"both":3}[hand]
    session.ready_score()
    final = state_at(session, step="tempo", mode="practice", hand="both",
                     bpm=40, running=True)
    assert final["kind"] == "perform"
    climb_to_mastery(session, "both", -1)
    assert {hand for hand, _ in visited} == {"right", "left", "both"}


def test_fake_keyboard_free_wrong_pause_resume_and_no_unearned_target(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    free = state_at(session, step="free", mode="learn", paused=False)
    expected = free["teaching"]["expected_notes"][0]["pitch"]
    session.reach_free_target()
    session.strike(61)
    wrong = state_at(session, step="free")["teaching"]
    assert wrong["target_index"] == 0 and wrong["hint_reason"] == "wrong_note"
    assert wrong["hint_visible"]
    session.command("pause")
    held = state_at(session, step="free", paused=True)
    old_beat = held["clock_beat"]
    old_index = held["teaching"]["target_index"]
    session.tick(30)
    session.strike(expected)
    frozen = state_at(session, step="free", paused=True)
    assert frozen["teaching"]["target_index"] == old_index
    assert frozen["clock_beat"] == pytest.approx(old_beat)
    session.command("resume")
    state_at(session, step="free", paused=False)
    session.strike(expected)
    session.tick(.1)   # the found note counts once its movement ends
    corrected = state_at(session, step="free")["teaching"]
    assert corrected["target_index"] == 1 and not corrected["hint_visible"]
    session.finish_free()
    state_at(session, step="tempo", mode="practice", bpm=40)
    assert not any(step["completed"] for step in session.ask("lesson.overview")["steps"])


@pytest.mark.parametrize("fault", ["missed", "wrong", "late", "extra"])
def test_fake_keyboard_failed_take_transitions_to_repeat_and_floor_free(practice_session, fault):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    session.ready_score()
    state_at(session, step="tempo", bpm=40)
    repeated, events = failed_take(session, fault=fault)
    state_at(session, step="tempo", bpm=40, running=True)
    if fault == "late":
        assert any(e.get("kind") == "attack" and e.get("status") == "late"
                   for e in events), events
    elif fault in ("wrong","extra"):
        assert any(e.get("kind") == "attack" and e.get("status") == "unexpected"
                   for e in events), events
    assert repeated["lesson_steps_mastered"] == 0
    # A second failure at the 50% floor returns to untimed original notes.
    at_floor = session.play_take(correct=False)
    assert at_floor["flow"]["step"] == "free"
    assert at_floor["lesson_level"] == "original"
    assert at_floor["mastered"] == 0


def test_fake_keyboard_repeated_floor_failures_choose_real_aid_and_original_return(practice_session):
    session = practice_session(bars=1, chords=True)
    session.finish_listen()
    original = session.ask("score.semantic")
    session.finish_free()
    for _ in range(2):
        session.play_take(correct=False)
    first = state_at(session, step="free", mode="learn")
    assert first["lesson_level"] == "original" and first["mastered"] == 0
    # The first floor-failure return offers no aid; only the second does.
    assert "Simplified:" not in first["flow"]["message"]
    assert not first["guided_recovery"]
    session.finish_free()
    for _ in range(2):
        session.play_take(correct=False)
    aid = state_at(session, step="free", mode="learn")
    assert aid["lesson_level"] == "original"
    assert "Simplified:" in aid["flow"]["message"]
    assert aid["guided_recovery"]
    # The curriculum still identifies the original source and grants no
    # mastery. The active SCORE, not the source label, must contain a real
    # reduced set of attacks from the selected Coda/Fukuda contribution.
    simplified = session.ask("score.semantic")
    assert len(simplified["notes"]) < len(original["notes"])
    assert {n["id"] for n in simplified["notes"]} < {n["id"] for n in original["notes"]}
    assert aid["mastered"] == 0
    session.finish_free()
    restored = state_at(session, step="free", mode="learn")
    assert restored["lesson_level"] == "original"
    assert {n["id"] for n in session.ask("score.semantic")["notes"]} == {
        n["id"] for n in original["notes"]}
    session.open()
    reopened = state_at(session, step="free", mode="learn", hand="right")
    assert reopened["teaching"]["target_index"] == 0
    assert not any(step["completed"] for step in session.ask("lesson.overview")["steps"])


def test_fake_keyboard_count_in_pause_and_failure_never_grade_unplayed_music(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    session.ready_score()
    active = state_at(session, step="tempo", mode="practice", running=True)
    current = active["playback_timeline"]["current"]
    session.strike(72)  # During the count-in: nothing is graded yet.
    assert session.snapshot()["midi_notes"] == 0
    session.clock.at = current["deadline_ms"]/1000+.5
    session.command("pause")
    state_at(session, paused=True)
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 0
    resumed = session.command("resume")
    assert resumed["running"] and not resumed["paused"]
    again = resumed["playback_timeline"]["current"]
    assert again["take_id"] == current["take_id"]
    # The take continues after its own count-in on the musical timeline.
    assert again["deadline_ms"]/1000 > session.clock()
    session.strike(72)  # During the resumed count-in, still ungraded.
    assert session.snapshot()["midi_notes"] == 0
    session.clock.at = again["deadline_ms"]/1000
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 1
    # Real graphical failure stops assessment and cannot grant mastery.
    session.ask("playback.failure",take_id=again["take_id"],
                segment_id=again["segment_id"],reason="retained score lost")
    stopped = state_at(session, running=False)
    assert stopped["mastered"] == 0 and stopped["playback_timeline"]["failure"]
    retry = session.command("restart")["playback_timeline"]["current"]
    assert retry and retry["take_id"] != again["take_id"]


def test_fake_keyboard_disconnection_during_take_cannot_award_lesson_progress(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    session.ready_score()
    state = state_at(session, step="tempo", running=True)
    start = take(state)["deadline_ms"]/1000
    session.clock.at = start
    port = session.engine.midi.port
    port.send(72, True)
    port.send(72, False)
    assert session.snapshot()["midi_notes"] == 1
    session.ask("midi.device.select",name="")
    broken = state_at(session, running=False)
    assert not broken["device"] and broken["mastered"] == 0
    assert port.closed
    session.tick(30)
    assert not any(step["completed"] for step in session.ask("lesson.overview")["steps"])
    session.ask("midi.device.select",name="Test piano")
    assert not session.snapshot()["running"]
    session.open()
    reopened = state_at(session, step="free", mode="learn", hand="right")
    assert reopened["teaching"]["target_index"] == 0
    assert reopened["mastered"] == 0

def test_navigation_suspend_is_one_way_and_preserves_the_real_paused_take(practice_session):
    """Leaving Practice must not accidentally Resume or advance a take."""
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    active = session.ready_score()
    assert active["running"] and active["controls"]["pause"]["action"] == "pause"
    before = active["transport_id"]
    first = session.command("ui_suspend")
    assert first["paused"] and first["transport_id"] == before
    assert first["controls"]["pause"]["action"] == "resume"
    session.tick(30)
    repeated = session.command("ui_suspend")
    assert repeated["paused"] and repeated["transport_id"] == before
    assert repeated["midi_notes"] == first["midi_notes"]
    assert repeated["mastered"] == first["mastered"]


def test_stop_during_count_in_without_renderer_fields_cancels_the_take(practice_session):
    """A damaged/unavailable native renderer may never disable emergency Stop."""
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert state["running"] and state["phase"] == "count_in", state
    assert state["controls"]["stop"]["enabled"]
    stopped = session.command("ui_stop")  # Deliberately no score_* fields.
    assert not stopped["running"] and not stopped["paused"]
    assert stopped["playback_intent"] is None
    assert stopped["musical_timeline"] is None
    assert stopped["mastered"] == 0
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 0


def test_real_lesson_passage_shortcuts_keep_exercise_not_skip_semantics(practice_session):
    session = practice_session(bars=3)
    session.finish_listen()
    original = session.snapshot()
    assert original["exercise"] == 1 and original["exercise_count"] > 1
    assert not original["controls"]["passage_previous"]["enabled"]
    assert original["controls"]["passage_next"]["action"] == "next"
    forward = session.command(
        "ui_passage_next", score_ready=False,
        score_revision=original["revision"],
        score_fingerprint=original["piece_fingerprint"])
    assert forward["exercise"] == 2
    assert forward["controls"]["passage_previous"]["enabled"]
    assert forward["mastered"] == original["mastered"]
    back = session.command(
        "ui_passage_previous", score_ready=False,
        score_revision=forward["revision"],
        score_fingerprint=forward["piece_fingerprint"])
    assert back["exercise"] == 1
    assert back["mastered"] == original["mastered"]
    assert back["controls"]["passage_previous"]["action"] == ""


def test_real_state_rejects_missing_control_and_timeline(practice_session):
    """A malformed published snapshot must not be consumed by Godot."""
    from copy import deepcopy
    from piano_teacher.state_contract import problems

    session = practice_session(bars=1)
    session.finish_listen()
    valid = session.snapshot()
    assert not problems(valid), problems(valid)
    missing = deepcopy(valid)
    del missing["controls"]["primary"]["enabled"]
    assert any("controls.primary" in issue for issue in problems(missing))
    missing = deepcopy(valid)
    del missing["playback_timeline"]
    assert any("playback_timeline" in issue for issue in problems(missing))

@pytest.mark.parametrize("grade_holds,next_bpm", [
    (False,"faster"), (True,40),
], ids=["pedal-friendly-default","strict-held-release"])
def test_real_midi_release_setting_changes_tempo_credit(
        practice_session, grade_holds, next_bpm):
    """The same physical early release is advisory unless hold grading is on."""
    session = practice_session(bars=1, single=True)
    session.ask("settings.update", grade_note_holds=grade_holds)
    session.finish_listen()
    session.finish_free()
    active = session.ready_score()
    assert active["flow"]["step"] == "tempo" and active["bpm"] == 40
    semantic = session.ask("score.semantic")
    assert len(semantic["notes"]) == 1
    note = semantic["notes"][0]
    assert note["duration_beats"] >= 3.0
    start = take(active)["deadline_ms"]/1000
    session.clock.at = start
    session.engine.midi.port.send(int(note["midi_pitch"]),True)
    session.clock.at = start + .15*60/active["bpm"]
    session.engine.midi.port.send(int(note["midi_pitch"]),False)
    changed = session.play_take(correct=False)
    assert changed["flow"]["step"] == "tempo"
    assert changed["bpm"] > 40 if next_bpm == "faster" else changed["bpm"] == next_bpm
    assert changed["mastered"] == 0

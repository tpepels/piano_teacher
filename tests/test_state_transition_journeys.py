"""Player-visible state journeys through the production engine and fake MIDI port.

Fake time and MIDI input are test stimuli only: the engine owns all lesson,
transport, grading, feedback and persistence decisions. No simulated state
machine or replacement evaluator is involved.
"""
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
    assert state["score_queue_next"]["transport_id"] == state["transport_id"]
    start = state["score_queue_next"]["deadline_at_ms"] / 1000
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
        # 50%, +10% of target, then two clean target takes. Every attack
        # and release is sent through the test's real MIDI callback.
        for bpm in (40, 48, 56, 64, 72, 80, 80):
            state_at(session, step="tempo", hand=hand, bpm=bpm, running=True)
            visited.append((hand, bpm))
            session.play_take()
        overview = session.ask("lesson.overview")["steps"]
        assert overview[{"right": 0, "left": 1, "both": 2}[hand]]["completed"]
        assert session.snapshot()["mastered"] == {"right":1,"left":2,"both":3}[hand]
    session.ready_score()
    final = state_at(session, step="tempo", mode="practice", hand="both",
                     bpm=40, running=True)
    assert final["kind"] == "perform"
    for bpm in (40, 48, 56, 64, 72, 80, 80):
        state_at(session, step="tempo", hand="both", bpm=bpm, running=True)
        session.play_take()
    assert session.ask("lesson.overview")["steps"][-1]["completed"]
    assert len(visited) == 21


def test_fake_keyboard_free_wrong_pause_resume_and_no_unearned_target(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    free = state_at(session, step="free", mode="learn", paused=False)
    expected = free["teaching"]["expected_notes"][0]["pitch"]
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
    session.finish_free()
    for _ in range(2):
        session.play_take(correct=False)
    aid = state_at(session, step="free", mode="learn")
    progress = session.engine.source_identity.plan.teaching_progress()
    counts = dict(progress.free_returns)
    assert counts.get(session.engine.source_identity.plan.identity,0) == 2, (
        counts, progress, aid["flow"])
    assert aid["lesson_level"] == "original"
    assert "Simplified:" in aid["flow"]["message"]
    assert aid["guided_recovery"] and session.engine.attempt.remediation_active is not None
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


def test_fake_keyboard_presentation_failure_and_resume_never_grade_unpresented_music(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.commands.require_presentation()
    session.finish_free()
    session.ready_score()
    intent = state_at(session, step="tempo", mode="practice", running=False)["playback_intent"]
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 0
    values = {k: intent[k] for k in ("intent_id", "attempt", "take_id",
                                    "fingerprint", "stage_key", "revision", "hand")}
    sample = session.clock()*1000.0
    values.update(source_from_beat=intent["from_beat"],
                  source_end_beat=intent["end_beat"],
                  sampled_at_ms=sample,
                  travel_ms=intent["earliest_deadline_ms"]-sample,
                  world_origin=100.0,queue_generation=1,
                  renderer_generation=intent["revision"])
    receipt = session.ask("playback.reserve", **values)
    assert not session.snapshot()["running"] and session.snapshot()["midi_notes"] == 0
    sampled = session.clock()*1000.0
    session.ask("playback.present", intent_id=intent["intent_id"],
                attempt=intent["attempt"],segment_id=receipt["segment_id"],
                physical_world_origin=receipt["world_origin"],
                physical_sampled_at_ms=sampled,
                physical_travel_ms=receipt["deadline_ms"]-sampled,
                physical_queue_generation=receipt["queue_generation"]+1,
                physical_renderer_generation=intent["revision"])
    active = state_at(session, running=True)
    assert active["transport_id"] >= 1
    session.command("pause")
    frozen = state_at(session, paused=True)
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 0
    resumed = session.command("resume")["playback_intent"]
    assert resumed["take_id"] == intent["take_id"]
    new_values = dict(values)
    new_values.update(intent_id=resumed["intent_id"],attempt=resumed["attempt"],
                      sampled_at_ms=session.clock()*1000.0,
                      travel_ms=20000.0,
                      renderer_generation=resumed["revision"],queue_generation=2,
                      take_id=resumed["take_id"])
    fresh = session.ask("playback.reserve", **new_values)
    sampled = session.clock()*1000.0
    session.ask("playback.present",intent_id=resumed["intent_id"],
                attempt=resumed["attempt"],segment_id=fresh["segment_id"],
                physical_world_origin=fresh["world_origin"],
                physical_sampled_at_ms=sampled,
                physical_travel_ms=fresh["deadline_ms"]-sampled,
                physical_queue_generation=fresh["queue_generation"]+1,
                physical_renderer_generation=resumed["revision"])
    session.strike(72)  # During the resumed count-in, still ungraded.
    assert session.snapshot()["midi_notes"] == 0
    session.clock.at = fresh["deadline_ms"]/1000
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 1
    # Real graphical failure stops assessment and cannot grant mastery.
    session.ask("playback.failure",take_id=resumed["take_id"],
                segment_id=fresh["segment_id"],reason="retained score lost")
    stopped = state_at(session, running=False)
    assert stopped["mastered"] == 0 and stopped["playback_timeline"]["failure"]
    session.command("restart")
    retry = session.snapshot()["playback_intent"]
    assert retry and retry["take_id"] != resumed["take_id"]


def test_fake_keyboard_disconnection_during_take_cannot_award_lesson_progress(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    session.ready_score()
    state = state_at(session, step="tempo", running=True)
    start = state["score_queue_next"]["deadline_at_ms"]/1000
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

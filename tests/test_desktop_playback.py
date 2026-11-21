"""Desktop command boundaries prevent grading music that was never presented.

The caller supplies admission facts, not a renderer or a second transport.
Actual Godot score admission is covered by the native behaviour group.
"""
import json

import pytest

from piano_teacher.inprocess import INVALID


def desktop_tempo(session):
    session.finish_listen()
    session.commands.require_presentation()
    session.finish_free()
    return session.ready_score()["playback_intent"]


def reserve(session, intent, **changes):
    values = {key: intent[key] for key in (
        "intent_id", "attempt", "take_id", "fingerprint", "stage_key", "revision", "hand")}
    sampled_ms = session.clock() * 1000.0
    physical_ms = (intent["fixed_deadline_ms"] if intent["fixed_deadline_ms"] is not None
                   else intent["earliest_deadline_ms"])
    values.update(source_from_beat=intent["from_beat"], source_end_beat=intent["end_beat"],
                  sampled_at_ms=sampled_ms, travel_ms=physical_ms-sampled_ms,
                  world_origin=100.0, queue_generation=1,
                  renderer_generation=intent["revision"])
    values.update(changes)
    return session.ask("playback.reserve", **values)


def present(session, intent, receipt):
    return session.ask("playback.present", intent_id=intent["intent_id"],
                       attempt=intent["attempt"], segment_id=receipt["segment_id"])


def rejected(session, operation, **payload):
    status, body = session.commands.request(operation, json.dumps(payload))
    assert status == INVALID, body.decode()
    assert json.loads(body)["error"]


def test_only_presented_score_starts_grading_and_repeated_acknowledgement_is_safe(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    assert intent and not session.snapshot()["running"]
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 0
    receipt = reserve(session, intent)
    assert not session.snapshot()["running"]
    result = present(session, intent, receipt)
    assert result["authorized"] and session.snapshot()["running"]
    assert present(session, intent, receipt) == result
    assert session.snapshot()["transport_id"] == result["transport_id"]
    status = session.ask("playback.status")  # Recover an acknowledgement lost by the caller.
    assert status["active_segment_id"] == receipt["segment_id"]
    assert status["active_take_id"] == intent["take_id"]
    session.clock.at = receipt["deadline_ms"]/1000
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 1
    session.tick()  # The production worker, rather than a read, accepts time transitions.
    assert session.snapshot()["playback_timeline"]["state"] == "playing"


def test_expired_admission_can_retry_without_starting_a_partial_count_in(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    receipt = reserve(session, intent)
    session.clock.at = receipt["deadline_ms"]/1000-1
    rejected(session, "playback.present", intent_id=intent["intent_id"],
             attempt=intent["attempt"], segment_id=receipt["segment_id"])
    assert not session.snapshot()["running"]
    retry = session.snapshot()["playback_intent"]
    rejected(session, "playback.present", intent_id=intent["intent_id"],
             attempt=intent["attempt"], segment_id=receipt["segment_id"])
    fresh = reserve(session, retry, travel_ms=20000.0)
    present(session, retry, fresh)
    assert session.snapshot()["running"]
    assert session.snapshot()["countdown"] >= 6
    assert session.snapshot()["mastered"] == 0


def test_withdrawn_or_different_source_cannot_authorize_old_music(practice_session):
    session = practice_session(bars=2)
    intent = desktop_tempo(session)
    receipt = reserve(session, intent)
    session.ask("playback.withdraw", intent_id=intent["intent_id"],
                attempt=intent["attempt"], reason="Score could not fit before its deadline")
    rejected(session, "playback.present", intent_id=intent["intent_id"],
             attempt=intent["attempt"], segment_id=receipt["segment_id"])
    session.select(2, 2)
    rejected(session, "playback.present", intent_id=intent["intent_id"],
             attempt=intent["attempt"], segment_id=receipt["segment_id"])
    assert session.snapshot()["first_bar"] == 2
    assert not session.snapshot()["running"]
    assert session.snapshot()["mastered"] == 0


def test_display_failure_stops_the_take_and_retry_uses_a_new_take(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    receipt = reserve(session, intent)
    present(session, intent, receipt)
    rejected(session, "playback.failure", take_id="old take", segment_id=receipt["segment_id"],
             reason="Score stopped drawing")
    assert session.snapshot()["running"]
    session.ask("playback.failure", take_id=intent["take_id"], segment_id=receipt["segment_id"],
                reason="Score stopped drawing")
    stopped = session.snapshot()
    assert not stopped["running"] and stopped["mastered"] == 0
    assert stopped["playback_timeline"]["failure"]
    session.command("restart")
    retry = session.ready_score()["playback_intent"]
    fresh = reserve(session, retry)
    present(session, retry, fresh)
    assert session.snapshot()["running"]
    assert retry["take_id"] != intent["take_id"]


def test_paused_count_in_resumes_the_same_take_and_rejects_lead_in_notes(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    receipt = reserve(session, intent)
    original = present(session, intent, receipt)
    session.clock.at = receipt["deadline_ms"]/1000-3
    session.command("pause")
    assert session.snapshot()["paused"]
    session.tick(30)
    resumed = session.command("resume")["playback_intent"]
    assert resumed["take_id"] == intent["take_id"]
    assert resumed["resume_remaining_beats"] == pytest.approx(2)
    fresh = reserve(session, resumed, reused_count_in=True)
    present(session, resumed, fresh)
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 0
    session.clock.at = fresh["deadline_ms"]/1000
    session.strike(72)
    after = session.snapshot()
    assert after["midi_notes"] == 1
    assert after["transport_id"] == original["transport_id"]


def test_listen_audio_and_lighting_wait_for_the_presented_score(practice_session):
    session = practice_session(bars=1)
    session.commands.require_presentation()
    audio = session.wait_audio()
    session.ready_score()
    state = session.command("demo_ready", token=audio["token"])
    intent = state["playback_intent"]
    assert intent["mode"] == "listen" and not state["running"]
    receipt = reserve(session, intent)
    assert not session.snapshot()["running"]
    present(session, intent, receipt)
    assert session.snapshot()["playback_timeline"]["current"]["graded"] is False
    session.clock.at = receipt["deadline_ms"]/1000+audio["duration_seconds"]+.01
    state = session.tick()
    assert state["flow"]["step"] == "free"
    assert state["mastered"] == 0
    assert not any(event.get("graded") for event in session.ask("feedback.events")["events"])


def test_automatic_repeat_keeps_its_one_bar_deadline_through_desktop_admission(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    # Real desktop score assets are prepared before this admission receipt.
    # Previously the musical-tick engraving fallback hid the omitted step.
    session.ask("score.native_layout")
    receipt = reserve(session, intent)
    initial = present(session, intent, receipt)
    for bpm, next_bpm in ((40,48), (48,56), (56,64), (64,72), (72,80), (80,80)):
        start = receipt["deadline_ms"]/1000
        for beat, pitch, on in ((0,72,True), (1,72,False), (3,79,True), (4,79,False)):
            session.clock.at = start+beat*60/bpm
            session.key(pitch, on, after=0)
        state = session.tick(.001)
        incoming = state["playback_intent"]
        assert incoming["action"] == "auto" and incoming["bpm"] == next_bpm
        assert incoming["fixed_deadline_ms"]/1000 == pytest.approx(start+4*60/bpm+4*60/next_bpm)
        if bpm == 80:
            assert state["streak"] == 1 and "1/2" in state["next_action"]
        final = [event for event in session.ask("feedback.events")["events"]
                 if event.get("final") and event["kind"] == "assessment"
                 and event["transport_id"] == initial["transport_id"]]
        assert len(final) == 2
        # A successor's source/revision must also be prepared off the clock.
        session.ask("score.native_layout")
        receipt = reserve(session, incoming)
        result = present(session, incoming, receipt)
        assert result["transport_id"] != initial["transport_id"]
        assert session.snapshot()["bpm"] == next_bpm and session.snapshot()["running"]
        initial = result

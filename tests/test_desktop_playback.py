"""Desktop command boundaries prevent grading music that was never presented.

The caller supplies admission facts, not a renderer or a second transport.
Actual Godot score admission is covered by the native behaviour group.
"""
import json

import pytest

from piano_teacher.inprocess import INVALID


def desktop_tempo(session):
    session.finish_listen()
    session.finish_free()
    return session.ready_score(admit=False)["playback_intent"]


def physical_offer(session, intent, **changes):
    """The native renderer's immutable physical witness, never a deadline."""
    return session.physical_offer(intent, **changes)


def reserve(session, intent, **changes):
    return session.ask("playback.reserve", **physical_offer(session, intent, **changes))


def physical_attestation(session, intent, receipt, **changes):
    """Test-only renderer fact, never a replacement musical scheduler."""
    sampled = session.clock()*1000.0
    values = {
        "physical_world_origin":receipt["world_origin"],
        "physical_sampled_at_ms":sampled,
        "physical_travel_ms":receipt["deadline_ms"]-sampled,
        "physical_queue_generation":receipt["queue_generation"]+1,
        "physical_renderer_generation":intent["revision"],
    }
    values.update(changes)
    return values


def present(session, intent, receipt, **changes):
    return session.ask("playback.present", intent_id=intent["intent_id"],
                       attempt=intent["attempt"], segment_id=receipt["segment_id"],
                       **physical_attestation(session,intent,receipt,**changes))


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
    # The physically armed score is valid, but the original musical
    # count-in has already passed. This must expire the attempt (rather
    # than only rejecting an absent new physical attestation).
    rejected(session, "playback.present", intent_id=intent["intent_id"],
             attempt=intent["attempt"], segment_id=receipt["segment_id"],
             **physical_attestation(session,intent,receipt))
    assert not session.snapshot()["running"]
    retry = session.snapshot()["playback_intent"]
    assert retry["attempt"] == intent["attempt"]+1
    rejected(session, "playback.present", intent_id=intent["intent_id"],
             attempt=intent["attempt"], segment_id=receipt["segment_id"],
             **physical_attestation(session,intent,receipt))
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
    retry = session.ready_score(admit=False)["playback_intent"]
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
    assert resumed["count_in_beats"] == pytest.approx(4)
    assert resumed["earliest_deadline_ms"] > session.clock()*1000
    fresh = reserve(session, resumed)
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
    for bpm, next_bpm in ((40,56), (56,72), (72,80), (80,80)):
        start = receipt["deadline_ms"]/1000
        for beat, pitch, on in ((0,72,True), (1,72,False), (3,79,True), (4,79,False)):
            session.clock.at = start+beat*60/bpm
            session.key(pitch, on, after=0)
        state = session.tick(.001)
        incoming = state["playback_intent"]
        assert incoming["action"] == "auto" and incoming["bpm"] == next_bpm
        # The written rest remains on the outgoing source's clock. A
        # faster next tempo begins only at the accepted new downbeat;
        # using next_bpm here caused an actual native ink collision.
        assert incoming["fixed_deadline_ms"]/1000 == pytest.approx(
            start+4*60/bpm+4*60/bpm)
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

# V1/V3 real-path scenario coverage: actual in-process engine, canonical
# lesson/session transition owners and fixture-injected MIDI note signals.


def test_lost_reserve_ack_recovers_original_immutable_witness(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    # Use a physically safe long future slot so the ACK can be lost
    # for longer than the witness's allowed sampling age while leaving
    # enough *full count-in* time for a later playback.present.
    offer = physical_offer(session, intent, travel_ms=20000.0)
    original = session.ask("playback.reserve", **offer)
    status = session.ask("playback.status")
    assert status["state"] == "reserved"
    assert status["reservation"] == original
    assert not session.snapshot()["running"]
    # An exact retransmission after the sample ages out is idempotent.
    session.clock.at += 2.5
    assert session.ask("playback.reserve", **offer) == original
    assert session.ask("playback.status")["reservation"] == original
    assert present(session, intent, original)["authorized"]
    assert session.ask("playback.status")["reservation"] is None


@pytest.mark.parametrize("mutate", [
    {"world_origin": 101.0},
    {"queue_generation": 2},
    {"renderer_generation": -1},
    {"travel_ms": 1.0},
    {"sampled_at_ms": -1.0},
])
def test_recovered_reservation_rejects_changed_renderer_witness(practice_session, mutate):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    offer = physical_offer(session, intent)
    receipt = session.ask("playback.reserve", **offer)
    rejected(session, "playback.reserve", **{**offer, **mutate})
    status = session.ask("playback.status")
    assert status["reservation"] == receipt
    assert status["reserved_segment_id"] == receipt["segment_id"]
    assert not session.snapshot()["running"]
    assert present(session, intent, receipt)["authorized"]


def test_stale_physical_offer_never_creates_a_backend_receipt(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    offer = physical_offer(session, intent)
    session.clock.at += 2.5
    rejected(session, "playback.reserve", **offer)
    assert session.ask("playback.status")["reservation"] is None
    assert session.snapshot()["playback_intent"]["intent_id"] == intent["intent_id"]
    assert not session.snapshot()["running"]


def test_three_failed_physical_attempts_end_admitting(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    attempts = []
    for _ in range(3):
        attempts.append(intent["attempt"])
        withdrawn = session.ask("playback.withdraw", intent_id=intent["intent_id"],
                                attempt=intent["attempt"],
                                reason="Simulated native queue could not reserve")
        intent = session.snapshot().get("playback_intent")
        if intent is None:
            assert withdrawn["abandoned"]
            break
        assert not withdrawn["abandoned"]
        assert withdrawn["next_attempt"] == intent["attempt"]
    state = session.snapshot()
    assert attempts == [0, 1, 2]
    assert intent is None
    assert state["playback_timeline"]["state"] == "failed"
    assert state["phase"] != "admitting"
    assert "native queue" in state["feedback"]
    assert not state["running"]
    issued = session.ask("playback.status")["intents_issued"]
    failure_text = state["feedback"]
    # Repeated score-ready acknowledgements and worker ticks cannot turn a
    # terminal source failure into new intents or replace its notice.
    for _ in range(4):
        session.command("score_ready", revision=state["revision"])
        later = session.tick(.25)
        assert later["playback_intent"] is None
        assert later["playback_timeline"]["state"] == "failed"
        assert not later["running"]
        assert later["feedback"] == failure_text
    assert session.ask("playback.status")["intents_issued"] == issued


def test_unready_score_timeout_does_not_leave_endless_admitting(practice_session):
    session = practice_session(bars=1)
    desktop_tempo(session)
    assert session.snapshot()["phase"] == "admitting"
    state = session.tick(121.0)
    assert state["playback_intent"] is None
    assert state["playback_timeline"]["state"] == "failed"
    assert state["phase"] != "admitting"
    assert not state["running"]
    assert state["next_action"]


def test_failed_authorized_take_cannot_replay_its_old_receipt(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    receipt = reserve(session, intent)
    present(session, intent, receipt)
    session.ask("playback.failure", take_id=intent["take_id"],
                segment_id=receipt["segment_id"],
                reason="Simulated authorized renderer disappeared")
    rejected(session, "playback.present", intent_id=intent["intent_id"],
             attempt=intent["attempt"], segment_id=receipt["segment_id"])
    assert not session.snapshot()["running"]
    assert session.snapshot()["playback_timeline"]["state"] == "failed"


def test_wrong_and_missing_fake_midi_do_not_complete_a_clean_take(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    receipt = reserve(session, intent)
    present(session, intent, receipt)
    previous = session.snapshot()["mastered"]
    # This fixture's authentic right-hand pitches are 72 and 79.
    session.clock.at = receipt["deadline_ms"]/1000.0
    session.strike(60)
    session.tick(5.0*60.0/intent["bpm"])
    assert session.snapshot()["mastered"] == previous


def test_guided_plan_deadline_changes_only_with_authenticated_source():
    """No Free window inherits a prior source's possibly expired deadline."""
    from dataclasses import replace
    from piano_teacher.application.score_state_publisher import (
        ScoreProjectionFacts, ScoreStatePublisher)

    publisher = ScoreStatePublisher()
    template = ScoreProjectionFacts(
        fingerprint="piece", stage_key="window:1", revision=1,
        transport_id=10, mode="learn", running=False, paused=False,
        awaiting_score=False, bpm=40.0, presentation_bpm=40.0,
        run_at=0.0, play_from_beat=0.0, announced=None,
        announced_deadline=None, announcement_serial=0,
        scheduled_start=None, timeline={}, next_count_in_beats=4.0,
        next_count_in_meter=(4, 4), continuous_horizon_beats=4.0,
        duration_beats=4.0, has_source=True)
    state = {"phase": "guided_wait"}
    publisher.prepare_guided(state, template, now=100.0)
    initial = publisher.publish(dict(state), template)
    assert initial and initial["deadline_at_ms"] > 100_000
    # Re-polling the same source cannot create another guided plan.
    publisher.prepare_guided(state, template, now=101.0)
    assert publisher.publish(dict(state), template) == initial

    # The next Free window starts directly, without returning through
    # a timed/idle stage. It must obtain a fresh future authoring epoch.
    next_source = replace(template, stage_key="window:2", revision=2)
    assert publisher.publish(dict(state), next_source) is None
    publisher.prepare_guided(state, next_source, now=200.0)
    next_plan = publisher.publish(dict(state), next_source)
    assert next_plan and next_plan["deadline_at_ms"] > 200_000
    assert next_plan["plan_id"] != initial["plan_id"]
    # Any later handoff also invalidates the old Free plan.
    another_transport = replace(next_source, transport_id=11)
    assert publisher.publish(dict(state), another_transport) is None


def test_backend_publishes_hold_target_and_running_motion_without_ui_phase_policy():
    """Free and Pause target semantics are decided before Godot sees a frame."""
    from dataclasses import replace
    from piano_teacher.application.score_state_publisher import (
        ScoreProjectionFacts, ScoreStatePublisher)

    projector = ScoreStatePublisher()
    facts = ScoreProjectionFacts(
        fingerprint="piece", stage_key="window:1", revision=1,
        transport_id=1, mode="learn", running=False, paused=False,
        awaiting_score=False, bpm=40.0, presentation_bpm=40.0,
        run_at=0.0, play_from_beat=0.0, announced=None,
        announced_deadline=None, announcement_serial=0,
        scheduled_start=None, timeline={}, next_count_in_beats=4.0,
        next_count_in_meter=(4,4), continuous_horizon_beats=4.0,
        duration_beats=4.0, has_source=True)

    def motion(observation, context):
        state = dict(observation)
        projector.publish(state, context)
        return state["presentation_directive"]

    teaching = {"phase":"guided_wait", "teaching":{
        "expected_notes":[{"beat":1.0,"pitch":72},{"beat":0.5,"pitch":76}]}}
    assert motion(teaching, facts) == {"kind":"target","source_beat":0.5}
    assert motion(teaching, replace(facts, paused=True)) == {"kind":"hold"}
    assert motion({"phase":"guided_complete","teaching":{"expected_notes":[]}},
                  facts) == {"kind":"hold"}
    assert motion(teaching, replace(facts, awaiting_score=True)) == {"kind":"hold"}
    pending = replace(facts, mode="practice", timeline={
        "intent":{"intent_id":"next"}, "current":{"state":"awaiting_admission"}})
    assert motion({"phase":"admitting"}, pending) == {"kind":"hold"}
    authorized_predecessor = replace(pending,timeline={
        "intent":{"intent_id":"next"},
        "current":{"current":{"segment_id":"older"},"state":"playing"}})
    assert motion({"phase":"admitting"}, authorized_predecessor) == {"kind":"retain"}
    running = replace(pending, running=True)
    assert motion({"phase":"playing"}, running) == {
        "kind":"run","clear_target":True}
    assert motion({"phase":"ready"}, replace(pending,timeline={},
        running=False)) == {"kind":"run","clear_target":True}
    idle = replace(pending,timeline={
        "intent":None, "current":{"current":None,"state":"idle"}})
    assert motion({"phase":"ready"}, idle) == {"kind":"hold"}
    # Failed admission can retain the predecessor's historical segment.
    # That is not a licence to scroll forever with no playable tempo.
    old_source = {"segment_id":"old","take_id":"previous"}
    failed = replace(pending,timeline={
        "intent":None,"current":{"current":old_source,"state":"failed",
                                  "failure":"No physical source can be admitted"}})
    assert motion({"phase":"loading"}, failed) == {"kind":"hold"}
    # A pending valid successor may continue the old, already authorized
    # rest without inventing a second clock or resetting the world.
    still_pending = replace(pending,timeline={
        "intent":{"intent_id":"next"},
        "current":{"current":old_source,"state":"playing"}})
    assert motion({"phase":"admitting"}, still_pending) == {"kind":"retain"}


def test_real_state_contract_includes_authoritative_motion_directive(practice_session):
    from piano_teacher.state_contract import VERSION, problems
    session = practice_session(bars=1)
    result = session.snapshot()
    assert VERSION == 7
    assert "presentation_directive" in result
    assert result["presentation_directive"]["kind"] in (
        "hold", "target", "retain", "run")
    assert not problems(result), problems(result)


def test_command_reply_carries_backend_resolved_action_outside_state(practice_session):
    import json
    from piano_teacher.state_contract import problems
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    current = session.ready_score()
    payload = {"action":"ui_pause", "score_ready":True,
               "score_revision":current["revision"],
               "score_fingerprint":current["piece_fingerprint"]}
    status, body = session.commands.request(
        "practice.command", json.dumps(payload))
    assert status == 0, body.decode()
    reply = json.loads(body)
    assert reply["outcome"] == {
        "version":1, "executed":True, "action":"pause",
        "effects":{"navigate_practice":False,
                   "refresh_settings":False,"invalidate_lesson":False}}
    assert reply["state"]["paused"]
    assert "outcome" not in reply["state"]
    assert not problems(reply["state"]), problems(reply["state"])
    assert session.snapshot()["paused"]


def test_command_navigation_effects_are_projected_only_in_backend():
    from piano_teacher.application.control_projection import project_command_outcome
    assert project_command_outcome("select_step")["effects"]["navigate_practice"]
    assert project_command_outcome("learn_next")["effects"]["navigate_practice"]
    assert project_command_outcome("calibration_apply")["effects"]["refresh_settings"]
    assert project_command_outcome("reset_path")["effects"]["invalidate_lesson"]
    assert not project_command_outcome(None)["executed"]
    assert not project_command_outcome(None)["effects"]["navigate_practice"]


@pytest.mark.parametrize("phase,mode,auto,expected",[
    ("ready","practice",False,"start"),
    ("performance_complete","perform",True,"start"),
    ("feedback","practice",False,"restart"),
    ("feedback","practice",True,""),
    ("playing","practice",True,""),
    ("count_in","practice",False,""),
    ("ready","listen",False,""),
    ("guided_wait","learn",False,""),
])
def test_backend_exclusively_decides_midi_start_gesture(
        phase, mode, auto, expected):
    from piano_teacher.application.control_projection import (
        project_controls, resolve_ui_intent)
    facts = {"loaded":True, "device":"Connected MIDI",
             "mode":mode, "phase":phase, "auto":auto,
             "running":phase in ("playing","count_in"),
             "paused":False, "warmup":False}
    choice = project_controls(facts)["midi_start"]
    assert choice["action"] == expected
    assert choice["enabled"] == bool(expected)
    if expected:
        action, options = resolve_ui_intent(
            "ui_midi_start",facts,score_ready=True)
        assert action == expected and options == {}


@pytest.mark.parametrize("mutation", [
    {"physical_world_origin": "not-a-world-coordinate"},
    {"physical_queue_generation": -1},
    {"physical_renderer_generation": -1},
    {"physical_travel_ms": 0.0},
])
def test_uncommitted_or_wrong_physical_arm_does_not_start_take(practice_session, mutation):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    reserved = reserve(session, intent)
    rejected(session, "playback.present",
             intent_id=intent["intent_id"],
             attempt=intent["attempt"], segment_id=reserved["segment_id"],
             **physical_attestation(session,intent,reserved,**mutation))
    assert not session.snapshot()["running"]
    assert session.ask("playback.status")["reserved_segment_id"] == reserved["segment_id"]
    assert present(session,intent,reserved)["authorized"]


def test_python_chooses_later_deadline_than_earliest_physical_clearance(practice_session):
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    minimum = physical_offer(session,intent,travel_ms=100.0)
    reserved = session.ask("playback.reserve",**minimum)
    assert reserved["deadline_ms"] >= intent["earliest_deadline_ms"]-.01
    assert reserved["deadline_ms"] > minimum["sampled_at_ms"]+minimum["travel_ms"]+1000
    assert not session.snapshot()["running"]
    assert present(session,intent,reserved,physical_world_origin=101.0)["authorized"]


def test_frozen_canvas_physical_world_can_shrink_as_deadline_approaches(practice_session):
    """World coordinates sampled in different frames are not ordered deadlines."""
    session = practice_session(bars=1)
    intent = desktop_tempo(session)
    offered = physical_offer(session, intent)
    receipt = session.ask("playback.reserve", **offered)
    assert not session.snapshot()["running"]
    # During Pause/Free/initial idle, the ink holds still but a candidate
    # future destination is expressed relative to the present frame.
    # Its remaining *world distance* shrinks as the same absolute
    # downbeat approaches. The accepted receipt must use the real
    # post-arm coordinate, not insist on increasing the old estimate.
    session.clock.at += .05
    fresh = physical_attestation(
        session, intent, receipt,
        physical_world_origin=receipt["world_origin"]-.05*intent["bpm"]/60.0)
    result = session.ask("playback.present",
        intent_id=intent["intent_id"],attempt=intent["attempt"],
        segment_id=receipt["segment_id"],**fresh)
    assert result["authorized"]
    active = session.snapshot()["playback_timeline"]["current"]
    assert active["world_origin"] == pytest.approx(fresh["physical_world_origin"])
    assert active["deadline_ms"] == receipt["deadline_ms"]
    assert active["segment_id"] == receipt["segment_id"]


def test_repeated_listen_audio_and_score_acks_cannot_reopen_failed_admission(practice_session):
    """The real Listen-ready worker may emit the same acknowledgements again."""
    session = practice_session(bars=1)
    session.ready_score()
    demo = session.wait_audio()
    session.command("demo_ready", token=demo["token"])
    pending = session.snapshot()["playback_intent"]
    assert pending and pending["action"] == "listen"
    started_issued = session.ask("playback.status")["intents_issued"]
    for attempt in range(3):
        pending = session.snapshot()["playback_intent"]
        assert pending and pending["attempt"] == attempt
        session.ask("playback.withdraw", intent_id=pending["intent_id"],
                    attempt=attempt,
                    reason="Native Listen geometry never became available")
    finished = session.snapshot()
    assert finished["playback_intent"] is None
    assert finished["playback_timeline"]["state"] == "failed"
    for _ in range(4):
        session.command("score_ready", revision=finished["revision"])
        session.command("demo_ready", token=demo["token"])
        session.tick(.25)
        observed = session.snapshot()
        assert observed["playback_intent"] is None
        assert observed["playback_timeline"]["state"] == "failed"
        assert not observed["running"]
    assert session.ask("playback.status")["intents_issued"] == started_issued


@pytest.mark.parametrize("next_action", ["score_ready", "auto"])
def test_delayed_automatic_ack_cannot_replace_matching_unpresented_take(
        practice_session, next_action):
    session = practice_session(bars=1)
    original = desktop_tempo(session)
    prior_issued = session.ask("playback.status")["intents_issued"]
    previous = session.snapshot()["playback_intent"]
    # A delayed score-ready acknowledgement or automatic worker tick
    # re-requests the same take; it must not issue a replacement intent.
    if next_action == "score_ready":
        session.command("score_ready", revision=previous["revision"])
    else:
        session.tick(.25)
    assert session.snapshot()["playback_intent"]["intent_id"] == original["intent_id"]
    assert session.snapshot()["playback_intent"]["take_id"] == original["take_id"]
    assert session.ask("playback.status")["intents_issued"] == prior_issued
    assert session.snapshot()["playback_intent"] == previous
    assert not session.snapshot()["running"]


def test_physical_key_instruction_uses_only_available_backend_action():
    from piano_teacher.application.control_projection import project_controls
    active = {"loaded":True, "device":"Test piano",
              "phase":"guided_complete","mode":"learn",
              "running":False,"paused":False}
    solo = project_controls(active)["midi_start"]
    assert solo["enabled"] and solo["action"] == "practice"
    course = project_controls({**active,"flow":{
        "step":"free","status":"Idea complete"}})["midi_start"]
    # The default Practice Flow transitions automatically: it must not
    # print a physical "press any key" instruction with no enabled action.
    assert not course["enabled"] and course["action"] == ""


def test_explicit_primary_recovers_after_terminal_automatic_admission_failure(practice_session):
    """A capped auto-retry must still expose a genuine user recovery route."""
    session = practice_session(bars=1)
    initial = desktop_tempo(session)
    for attempt in range(3):
        pending = session.snapshot()["playback_intent"]
        assert pending["attempt"] == attempt
        session.ask("playback.withdraw",intent_id=pending["intent_id"],
                    attempt=attempt,reason="Simulated physical stream unavailable")
    state = session.snapshot()
    assert state["playback_timeline"]["state"] == "failed"
    assert state["controls"]["primary"]["enabled"]
    assert state["controls"]["primary"]["action"] == "start"
    attempted = session.command(
        "ui_primary",score_ready=True,score_revision=state["revision"],
        score_fingerprint=state["piece_fingerprint"])
    if attempted["playback_intent"] is None:
        attempted = session.ready_score()
    assert attempted["playback_intent"] is not None
    assert attempted["playback_intent"]["intent_id"] != initial["intent_id"]
    assert attempted["playback_intent"]["attempt"] == 0
    assert attempted["playback_timeline"]["state"] == "awaiting_admission"
    assert not attempted["running"]


def test_navigation_suspend_preserves_pending_take_and_never_resumes_on_reentry(practice_session):
    """Real desktop admission: leaving during Play is a one-way Pause gesture."""
    session = practice_session(bars=1)
    pending = desktop_tempo(session)
    visible = session.snapshot()
    assert visible["phase"] == "admitting"
    assert visible["controls"]["pause"]["action"] == "pause"
    assert visible["controls"]["stop"]["enabled"]
    # The command is resolved against the SAME status as the screen, under
    # the engine lock. No renderer revision/readiness is needed to suspend.
    held = session.command("ui_suspend")
    assert held["paused"] and held["playback_intent"] is None
    assert not held["running"]
    assert held["controls"]["pause"]["action"] == "resume"
    again = session.command("ui_suspend")
    assert again["paused"] and again["playback_intent"] is None
    assert again["transport_id"] == held["transport_id"]
    # A deliberate Resume produces a new physical intent for the identical
    # selected musical take; leaving Practice did not auto-resume it.
    reopened = session.command(
        "ui_pause",score_ready=True,score_revision=again["revision"],
        score_fingerprint=again["piece_fingerprint"])
    assert not reopened["paused"]
    renewed = reopened["playback_intent"]
    assert renewed is not None and renewed["attempt"] == 0
    assert renewed["intent_id"] != pending["intent_id"]
    assert renewed["from_beat"] == pending["from_beat"]


def test_stop_cancels_unpresented_playback_without_renderer_identity(practice_session):
    """The S/Stop safety gesture survives a missing or obsolete score view."""
    session = practice_session(bars=1)
    pending = desktop_tempo(session)
    assert session.snapshot()["phase"] == "admitting"
    stopped = session.command("ui_stop")
    assert not stopped["running"] and not stopped["paused"]
    assert stopped["playback_intent"] is None
    assert stopped["controls"]["primary"]["enabled"]
    assert pending["intent_id"] != (
        stopped["playback_intent"] or {}).get("intent_id")
    # A delayed physical reserve from the canceled take must not start
    # grading after Stop, even when the renderer produces a valid witness.
    rejected(session,"playback.reserve",**physical_offer(session,pending))
    assert session.snapshot()["playback_intent"] is None


def test_source_independent_stop_halts_authorized_playback(practice_session):
    """Stop remains actionable when the native renderer has failed."""
    session = practice_session(bars=1)
    pending = desktop_tempo(session)
    receipt = reserve(session,pending)
    assert present(session,pending,receipt)["authorized"]
    assert session.snapshot()["running"]
    stopped = session.command("ui_stop")
    assert not stopped["running"] and not stopped["paused"]
    assert stopped["playback_intent"] is None
    assert stopped["feedback"] == "Stopped"

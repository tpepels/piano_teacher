"""Desktop playback: every timed take is placed on the musical timeline.

The engine places and starts each take itself; Godot only draws the
published timeline. These checks drive the in-process engine as the
desktop does and inspect what a player would notice.
"""
import json

import pytest

from piano_teacher.inprocess import INVALID
from piano_teacher.application.tempo_curve import count_in_spans, spans_seconds


def desktop_tempo(session):
    """Listen, Free, then the first Tempo take; returns its timeline entry."""
    session.finish_listen()
    session.finish_free()
    return session.ready_score()["playback_timeline"]["current"]


def rejected(session, operation, **payload):
    status, body = session.commands.request(operation, json.dumps(payload))
    assert status == INVALID, body.decode()
    assert json.loads(body)["error"]


def test_display_failure_stops_the_take_and_retry_uses_a_new_take(practice_session):
    session = practice_session(bars=1)
    take = desktop_tempo(session)
    rejected(session, "playback.failure", take_id="old take", segment_id=take["segment_id"],
             reason="Score stopped drawing")
    assert session.snapshot()["running"]
    session.ask("playback.failure", take_id=take["take_id"], segment_id=take["segment_id"],
                reason="Score stopped drawing")
    stopped = session.snapshot()
    assert not stopped["running"] and stopped["mastered"] == 0
    assert stopped["playback_timeline"]["failure"]
    session.command("restart")
    retry = session.ready_score()
    assert retry["running"]
    assert retry["playback_timeline"]["current"]["take_id"] != take["take_id"]


def test_paused_count_in_resumes_the_same_take_and_rejects_lead_in_notes(practice_session):
    session = practice_session(bars=1)
    take = desktop_tempo(session)
    original = session.snapshot()
    session.clock.at = take["deadline_ms"]/1000-3
    session.command("pause")
    assert session.snapshot()["paused"]
    session.tick(30)
    again = session.command("resume")["playback_timeline"]["current"]
    assert again["take_id"] == take["take_id"]
    # Paused in the count-in: the rest of it and the take move by exactly
    # the paused time; the drawn notes keep their place on the staff.
    assert again["deadline_ms"] == pytest.approx(take["deadline_ms"]+30000, abs=1)
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 0
    session.clock.at = again["deadline_ms"]/1000
    session.strike(72)
    after = session.snapshot()
    assert after["midi_notes"] == 1
    assert after["transport_id"] == original["transport_id"]


def test_listen_audio_and_lighting_wait_for_the_count_in(practice_session):
    session = practice_session(bars=1)
    audio = session.wait_audio()
    session.ready_score()
    state = session.command("demo_ready", token=audio["token"])
    current = state["playback_timeline"]["current"]
    assert state["mode"] == "listen" and state["running"]
    assert current["graded"] is False
    assert current["deadline_ms"]/1000 > session.clock()
    session.clock.at = current["deadline_ms"]/1000+audio["duration_seconds"]+.01
    state = session.tick()
    assert state["flow"]["step"] == "free"
    assert state["mastered"] == 0
    assert not any(event.get("graded") for event in session.ask("feedback.events")["events"])


def test_automatic_repeat_follows_after_one_count_in_bar(practice_session):
    session = practice_session(bars=1)
    take = desktop_tempo(session)
    session.ask("score.native_layout")
    initial = session.snapshot()
    # A short, precisely played window reaches the target in one take.
    for bpm, next_bpm in ((40,80), (80,80)):
        start = take["deadline_ms"]/1000
        for beat, pitch, on in ((0,72,True), (1,72,False), (3,79,True), (4,79,False)):
            session.clock.at = start+beat*60/bpm
            session.key(pitch, on, after=0)
        state = session.tick(.001)
        incoming = state["playback_timeline"]["current"]
        assert state["running"] and state["transport_id"] != initial["transport_id"]
        assert incoming["bpm"] == next_bpm
        # The window ends on its barline: no rest, then one count-in bar
        # whose first half eases from the outgoing to the incoming tempo.
        assert incoming["deadline_ms"]/1000 == pytest.approx(
            start+4*60/bpm+spans_seconds(count_in_spans(4,bpm,next_bpm)))
        if bpm == 80:
            assert state["streak"] == 1
        final = [event for event in session.ask("feedback.events")["events"]
                 if event.get("final") and event["kind"] == "assessment"
                 and event["transport_id"] == initial["transport_id"]]
        assert len(final) == 2
        take, initial = incoming, state


def test_wrong_and_missing_fake_midi_do_not_complete_a_clean_take(practice_session):
    session = practice_session(bars=1)
    take = desktop_tempo(session)
    previous = session.snapshot()["mastered"]
    # This fixture's authentic right-hand pitches are 72 and 79.
    session.clock.at = take["deadline_ms"]/1000.0
    session.strike(60)
    session.tick(5.0*60.0/take["bpm"])
    assert session.snapshot()["mastered"] == previous


def test_source_independent_stop_halts_authorized_playback(practice_session):
    """Stop remains actionable when the native renderer has failed."""
    session = practice_session(bars=1)
    desktop_tempo(session)
    assert session.snapshot()["running"]
    stopped = session.command("ui_stop")
    assert not stopped["running"] and not stopped["paused"]
    assert stopped["playback_intent"] is None
    assert stopped["feedback"] == "Stopped"


def test_guided_plan_deadline_changes_only_with_authenticated_source():
    """No Free window inherits a prior source's possibly expired deadline."""
    from dataclasses import replace
    from piano_teacher.application.score_state_publisher import (
        ScoreProjectionFacts, ScoreStatePublisher)

    publisher = ScoreStatePublisher()
    template = ScoreProjectionFacts(
        fingerprint="piece", stage_key="window:1", revision=1,
        transport_id=10, mode="learn", running=False, paused=False,
        awaiting_score=False, bpm=40.0, timeline={}, next_count_in_beats=4.0,
        next_count_in_meter=(4, 4),
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
        awaiting_score=False, bpm=40.0, timeline={}, next_count_in_beats=4.0,
        next_count_in_meter=(4,4),
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
    assert VERSION == 10
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


def test_physical_key_instruction_uses_only_available_backend_action():
    from piano_teacher.application.control_projection import project_controls
    active = {"loaded":True, "device":"Test piano",
              "phase":"guided_complete","mode":"learn",
              "running":False,"paused":False}
    course = project_controls({**active,"flow":{
        "step":"free","status":"Idea complete"}})["midi_start"]
    # The default Practice Flow transitions automatically: it must not
    # print a physical "press any key" instruction with no enabled action.
    assert not course["enabled"] and course["action"] == ""


def test_keyboard_hint_only_for_a_wrong_note_in_free():
    """Owner-confirmed rule (previously checked in Godot): the keyboard is
    hidden except as the wrong-note hint in Free."""
    from piano_teacher.application.screen_projection import keyboard
    free = {"mode": "learn", "teaching": {"hint_visible": False}}
    assert keyboard(free) == "hidden"
    waiting = {"mode": "learn", "teaching": {"hint_visible": True, "hint_reason": "waiting"}}
    assert keyboard(waiting) == "hidden"
    wrong = {"mode": "learn", "teaching": {"hint_visible": True, "hint_reason": "wrong_note"}}
    assert keyboard(wrong) == "hint"
    for mode in ("practice", "listen"):
        assert keyboard({**wrong, "mode": mode}) == "hidden"

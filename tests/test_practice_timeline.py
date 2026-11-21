"""Count-in, repeated attempts and interruption use the published musical time."""
import pytest


@pytest.mark.parametrize("correct", [True,False], ids=["clean-faster","failed-same-tempo"])
def test_repeat_follows_held_ending_with_exactly_one_bar(practice_session, correct):
    session = practice_session(bars=1, first_attack=.5, held_tail=2)
    session.finish_listen()
    session.finish_free()
    before = session.ready_score()
    source = session.ask("score.semantic")
    outgoing_start = before["score_queue_next"]["deadline_at_ms"]/1000
    assert before["play_from_beat"] == .5
    assert source["duration_beats"] == 4
    assert source["practice_timeline"]["sounding_duration_beats"] == 6
    after = session.play_take(correct=correct)
    incoming = after["score_queue_next"]
    # A complete PRINTED rest belongs to the outgoing score clock (40),
    # even when success has selected the next take's faster 48 BPM.
    expected = outgoing_start+(6-.5)*60/40+4*60/40
    assert incoming["deadline_at_ms"]/1000 == pytest.approx(expected,abs=.001)
    assert incoming["transport_id"] == after["transport_id"]
    assert after["transport_id"] != before["transport_id"]
    assert incoming["count_in_beats"] == 4
    assert incoming["source_from_beat"] == .5
    assert incoming["bpm"] == (48 if correct else 40)


def test_count_in_uses_authored_six_eight_and_first_playable_attack(practice_session):
    session = practice_session(bars=1, meter=(6,8), first_attack=.5)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert state["count_in_meter"] == [6,8]
    assert state["count_in_beats"] == 3
    assert state["play_from_beat"] == .5
    assert min(note["onset_beats"] for note in session.ask("score.semantic")["notes"]) == .5


def test_pause_freezes_musical_time_and_resume_ignores_lead_in_keys(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    session.clock.at = state["score_queue_next"]["deadline_at_ms"]/1000+.5
    before = session.snapshot()
    session.command("pause")
    paused = session.tick(30)
    assert paused["paused"]
    assert paused["clock_beat"] == pytest.approx(before["clock_beat"])
    resumed = session.command("resume")
    assert resumed["transport_id"] == before["transport_id"]
    assert resumed["resume_count_in_beat"] < 0
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 0
    lead = -session.snapshot()["resume_count_in_beat"]*60/resumed["bpm"]
    after = session.tick(lead+.001)
    assert after["clock_beat"] >= before["clock_beat"]
    assert after["visual_scroll_beat"] >= before["visual_scroll_beat"]
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 1
    assert session.snapshot()["mastered"] == 0


def test_listen_again_returns_to_free_without_advancing_or_grading(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    session.ready_score()
    session.command("listen")
    listening = session.snapshot()
    assert listening["flow"]["step"] == "listen"
    assert listening["bpm"] == listening["target_bpm"] == 80
    session.strike(61)
    returned = session.finish_listen()
    assert returned["flow"]["step"] == "free"
    assert returned["lesson_step"] == 1 and returned["mastered"] == 0
    assert not session.ask("feedback.events")["events"] or all(
        not event.get("graded") for event in session.ask("feedback.events")["events"])


def test_unplug_after_the_last_attack_but_before_the_ending_cannot_award_progress(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    before = session.ready_score()
    start = before["score_queue_next"]["deadline_at_ms"]/1000
    session.clock.at = start
    session.strike(72)
    session.clock.at = start+4.5
    session.strike(79)
    assert session.snapshot()["midi_notes"] == 2
    session.ask("midi.device.select", name="")
    interrupted = session.tick(60)
    assert not interrupted["running"] and not interrupted["device"]
    assert interrupted["mastered"] == 0
    assert not any(step["completed"] for step in session.ask("lesson.overview")["steps"])
    reopened = session.open()
    assert reopened["hand"] == "right" and reopened["flow"]["step"] == "free"


def test_live_and_final_feedback_keep_the_same_authentic_source_heads(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    layout = session.ask("score.native_layout")
    state = session.ready_score()
    source = session.ask("score.semantic")["notes"]
    start = state["score_queue_next"]["deadline_at_ms"]/1000
    session.clock.at = start
    session.strike(source[0]["midi_pitch"])
    session.tick()
    live = [event for event in session.ask("feedback.events")["events"]
            if event["kind"] == "assessment"]
    assert {event["source_id"] for event in live} == {source[0]["id"]}
    assert all(not event["final"] for event in live)
    assert all(event["note_id"] == layout["attack_map"][event["source_id"]] for event in live)
    session.clock.at = start+4.5
    session.strike(source[1]["midi_pitch"])
    session.tick()
    after = session.play_take(correct=False)  # Inputs above are the completed take.
    final = [event for event in session.ask("feedback.events")["events"]
             if event["kind"] == "assessment" and event.get("final")]
    assert {event["source_id"] for event in final} == {note["id"] for note in source}
    assert all(event["transport_id"] == state["transport_id"] and event["release_advisory"] for event in final)
    assert all(event["note_id"] == layout["attack_map"][event["source_id"]] for event in final)
    assert after["bpm"] == 48  # Short releases remain acceptable in normal flow.

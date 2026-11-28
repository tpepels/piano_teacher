"""Count-in, repeated attempts and interruption use the published musical time."""
from session_inputs import take
import pytest


@pytest.mark.parametrize("correct", [True,False], ids=["clean-faster","failed-same-tempo"])
def test_repeat_follows_held_ending_with_exactly_one_bar(practice_session, correct):
    session = practice_session(bars=1, first_attack=.5, held_tail=2)
    session.finish_listen()
    session.finish_free()
    before = session.ready_score()
    source = session.ask("score.bundle")["model"]
    outgoing_start = take(before)["deadline_ms"]/1000
    assert before["play_from_beat"] == .5
    assert source["duration_beats"] == 4
    assert source["practice_timeline"]["sounding_duration_beats"] == 6
    after = session.play_take(correct=correct)
    incoming = take(after)
    # Ties retain their sounding end and repeat on the same world axis.
    # Sparse material begins at the original target tempo.
    from piano_teacher.application.tempo_curve import count_in_spans, spans_seconds
    bpm = before["bpm"]
    expected = (outgoing_start+(6-.5)*60/bpm+(8-6)*60/bpm
                +spans_seconds(count_in_spans(4,bpm,incoming["bpm"])))
    assert incoming["deadline_ms"]/1000 == pytest.approx(expected,abs=.001)
    assert incoming["transport_id"] == after["transport_id"]
    assert after["transport_id"] != before["transport_id"]
    assert incoming["count_in_beats"] == 4
    assert incoming["source"]["from_beat"] == .5
    assert incoming["bpm"] == before["bpm"] == 80
    assert after["streak"] == (1 if correct else 0)


def test_count_in_uses_authored_six_eight_and_first_playable_attack(practice_session):
    session = practice_session(bars=1, meter=(6,8), first_attack=.5)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert state["count_in_meter"] == [6,8]
    assert state["count_in_beats"] == 3
    assert state["play_from_beat"] == .5
    assert min(note["onset_beats"] for note in session.ask("score.bundle")["model"]["notes"]) == .5


def test_navigation_publishes_source_timing_before_notation(practice_session, monkeypatch):
    from piano_teacher.application import score_artifacts

    session = practice_session(bars=3, meter=(6, 8))

    def cannot_compile(*args, **kwargs):
        raise AssertionError("a musical snapshot compiled notation")

    monkeypatch.setattr(score_artifacts, "build_lesson_score", cannot_compile)
    session.select(2, 2)
    assert session.snapshot()["practice_timeline"]["gap"]["duration_beats"] == 3


def test_resume_after_playing_preserves_full_authored_five_four_count_in(practice_session):
    # A paused graded take must reopen with one complete authored measure,
    # including when the local meter has more than four quarter beats.
    session = practice_session(bars=1, meter=(5, 4))
    session.finish_listen()
    session.finish_free()
    active = session.ready_score()
    assert active["count_in_meter"] == [5, 4]
    assert active["count_in_beats"] == 5
    session.clock.at = take(active)["deadline_ms"] / 1000 + .5
    before = session.snapshot()
    session.command("pause")
    session.tick(1)
    resumed = session.admit(session.command("resume"))
    assert resumed["transport_id"] == before["transport_id"]
    assert resumed["count_in_meter"] == [5, 4]
    assert resumed["count_in_beats"] == 5
    # The take continues after its own count-in bar.
    assert take(resumed)["deadline_ms"]/1000 > session.clock()
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 0


def test_pause_freezes_musical_time_and_resume_ignores_lead_in_keys(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    session.clock.at = take(state)["deadline_ms"]/1000+.5
    before = session.snapshot()
    session.command("pause")
    paused = session.tick(30)
    assert paused["paused"]
    assert paused["clock_beat"] == pytest.approx(before["clock_beat"])
    resumed = session.admit(session.command("resume"))
    assert resumed["transport_id"] == before["transport_id"]
    lead = take(resumed)["deadline_ms"]/1000-session.clock()
    assert lead > 0
    session.strike(72)
    assert session.snapshot()["midi_notes"] == 0
    after = session.tick(lead+.001)
    assert after["clock_beat"] >= before["clock_beat"]
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
    start = take(before)["deadline_ms"]/1000
    session.clock.at = start
    session.strike(72)
    session.clock.at = start+3*60/before["bpm"]
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
    layout = session.ask("score.bundle")["layout"]
    state = session.ready_score()
    source = session.ask("score.bundle")["model"]["notes"]
    start = take(state)["deadline_ms"]/1000
    session.clock.at = start
    session.strike(source[0]["midi_pitch"])
    session.tick()
    live = [event for event in session.ask("feedback.events")["events"]
            if event["kind"] == "assessment"]
    assert {event["source_id"] for event in live} == {source[0]["id"]}
    assert all(not event["final"] for event in live)
    assert all(event["source_id"] in layout["attack_map"] and "note_id" not in event for event in live)
    session.clock.at = start+3*60/state["bpm"]
    session.strike(source[1]["midi_pitch"])
    session.tick()
    after = session.play_take(correct=False)  # Inputs above are the completed take.
    final = [event for event in session.ask("feedback.events")["events"]
             if event["kind"] == "assessment" and event.get("final")]
    assert {event["source_id"] for event in final} == {note["id"] for note in source}
    assert all(event["transport_id"] == state["transport_id"] and event["release_advisory"] for event in final)
    assert all(event["source_id"] in layout["attack_map"] and "note_id" not in event for event in final)
    assert after["bpm"] == state["bpm"] == 80 and after["streak"] == 1


@pytest.mark.parametrize("travel", [0.0, 9.5])
def test_free_holds_where_godot_can_draw_its_first_target(practice_session, travel):
    """Godot reports, with score_ready, how far ahead a Free passage may
    open (off-screen, after ink still on the staff). Python's Free hold is
    never nearer, so the staff stops exactly at the drawn target (owner
    report 2026-11-25: it stopped short of the line)."""
    session = practice_session(bars=2)
    command = session.command

    def with_geometry(action, **values):
        if action == "score_ready":
            values.update(placement_revision=values["revision"], free_travel_beats=travel)
        return command(action, **values)

    session.command = with_geometry
    session.finish_listen()
    state = session.snapshot()
    assert state["mode"] == "learn"
    hold = state["musical_timeline"]["segments"][-1]
    assert hold["kind"] == "hold"
    bar = 4.0   # 4/4: Free always travels at least one bar
    movement = state["musical_timeline"]["segments"][-2]
    assert movement["kind"] == "rest"
    assert movement["beats"] == pytest.approx(max(bar, travel))
    assert hold["world_start"] == pytest.approx(movement["world_start"]+movement["beats"])
    # It arrives after the travel at the piece's tempo, but within a few
    # seconds: on a long or slow travel the staff moves faster.
    deadline = state["playback_timeline"]["guided"]["deadline_at_ms"]/1000
    assert deadline-session.clock.at == pytest.approx(
        min(max(bar, travel)*60/state["bpm"], 3.0), abs=.01)


def test_a_return_to_free_uses_the_placement_facts_of_the_latest_poll(practice_session):
    """Two failures at the floor return to Free with no command from Godot;
    the facts it sends with every state poll place that Free (owner report
    2026-11-25: the returned Free stopped short of its target)."""
    from test_midi_journeys import play, tempo
    session = practice_session(bars=2, chords=True)
    state = tempo(session)
    state = play(session, state, missing=(1,2))
    session.ask("state.snapshot", placement_revision=state["revision"],
                free_travel_beats=9.5, ink_ahead_beats=0.0)
    free = play(session, state, missing=(1,2))
    assert (free["mode"], free["flow"]["step"]) == ("learn", "free")
    session.ask("state.snapshot", placement_revision=free["revision"],
                free_travel_beats=9.5, ink_ahead_beats=0.0)
    session.ask("state.snapshot", placement_revision=free["revision"]-1,
                free_travel_beats=18.0, ink_ahead_beats=18.0)
    session.ready_score()
    movement, hold = session.snapshot()["musical_timeline"]["segments"][-2:]
    assert hold["kind"] == "hold" and movement["kind"] == "rest"
    assert movement["beats"] == pytest.approx(9.5)
    assert hold["world_start"] == pytest.approx(movement["world_start"]+9.5)


def test_unknown_placement_facts_are_refused(practice_session):
    session = practice_session(bars=2)
    status, body = session.commands.request("state.snapshot", '{"travel":1}')
    assert status != 0 and b"Unknown placement facts" in body


@pytest.mark.parametrize("outgoing, incoming", [(40.0, 160.0), (120.0, 60.0)])
def test_return_to_free_preserves_projection_until_publication(outgoing, incoming):
    from piano_teacher.application.musical_timeline import (
        MOVE_LEAD_SECONDS,
        MusicalTimeline,
        TimelineSegment,
    )
    from piano_teacher.application.tempo_curve import TempoSpan

    timeline = MusicalTimeline()
    timeline.append(TimelineSegment(
        "take", 0.0, 10.0, (TempoSpan(4.0, outgoing, outgoing),),
        take_id="previous", mode="practice"))
    now = timeline.segments[-1].end_at + .25
    world = timeline.world_at(now)
    old = [timeline.world_at(now + delay)
           for delay in (0.0, .04, .08, MOVE_LEAD_SECONDS)]
    travel = 8.0
    timeline.start_free(now=now, travel_beats=travel, bpm=incoming)
    assert timeline.world_at(now) == pytest.approx(world)
    assert [timeline.world_at(now + delay)
            for delay in (0.0, .04, .08, MOVE_LEAD_SECONDS)] == pytest.approx(old)
    arrival = now + travel * 60.0 / incoming
    assert timeline.hold_open_at() == pytest.approx(arrival)
    assert timeline.world_at(arrival) == pytest.approx(world + travel)
    assert timeline.world_at(arrival + 10.0) == pytest.approx(world + travel)

"""Free's staff and when its keys count (code review 2026-11-25).

The staff stops exactly at each target, a key counts only once the target
is at rest there (docs/practice-flow.md, Free), and nothing the learner or
the piano does moves the staff away from the note still to be found.
"""
import mido
import pytest


def hold(session):
    segments = session.snapshot()["musical_timeline"]["segments"]
    assert segments[-1]["kind"] == "hold", segments[-1]
    return segments[-1]["world_start"]


def free(session):
    session.finish_listen()
    return session.reach_free_target()


def test_the_first_hold_is_at_the_first_target_not_the_window_opening(practice_session):
    # The window opens on beat 0 but its first note is on beat 2.
    session = practice_session(bars=2, first_attack=2.0)
    session.finish_listen()
    state = session.snapshot()
    first = state["teaching"]["expected_notes"][0]["beat"]
    assert first == 2.0
    # The same continuous world already contains the Listen passage.
    # Travel is measured from its final rest, not absolute world zero.
    segments = state["musical_timeline"]["segments"]
    travel = segments[-2]
    assert travel["kind"] == "rest"
    assert travel["beats"] == pytest.approx(4.0+first)
    assert hold(session) == pytest.approx(travel["world_start"]+travel["beats"])


def test_a_target_taken_back_in_the_same_movement_keeps_the_staff_on_it(practice_session):
    session = practice_session(bars=2)
    state = free(session)
    target = state["teaching"]["expected_notes"][0]["pitch"]
    before = hold(session)
    session.key(target, after=0)
    session.key(target+2, after=.03)      # a smudge within 80 ms
    session.key(target, False, after=0)
    session.key(target+2, False, after=0)
    after = session.tick(.2)
    assert after["teaching"]["target_index"] == 0
    assert hold(session) == pytest.approx(before)


def test_a_key_while_the_next_target_moves_in_earns_nothing(practice_session):
    session = practice_session(bars=2)
    state = free(session)
    session.strike(state["teaching"]["expected_notes"][0]["pitch"])
    moving = session.tick(.1)
    assert moving["teaching"]["target_index"] == 1
    flashes = moving["screen"]["flash"]["id"]
    session.strike(moving["teaching"]["expected_notes"][0]["pitch"])   # still moving
    early = session.tick(.02)
    assert early["teaching"]["target_index"] == 1
    assert early["screen"]["flash"]["id"] == flashes+1
    arrived = session.reach_free_target()
    session.strike(arrived["teaching"]["expected_notes"][0]["pitch"])
    found = session.tick(.1)
    # Found at rest: the window's second and last target completes Free.
    assert found["mode"] != "learn" or found["teaching"]["target_index"] == 2


def test_free_movement_uses_duration_target_without_excessive_acceleration(practice_session):
    session = practice_session(bars=2, bpm=20)     # a very slow piece
    state = free(session)
    session.strike(state["teaching"]["expected_notes"][0]["pitch"])
    session.tick(.1)
    segments = session.snapshot()["musical_timeline"]["segments"]
    move = segments[-2]
    assert move["kind"] == "rest"
    seconds = move["beats"]*60/move["spans"][0][1]
    # A 3-beat move cannot complete in 1.5 s at an 80 BPM cap.
    # Preserve the independent long-gap no-sprint requirement.
    assert move["spans"][0][1] == pytest.approx(min(80, max(20, move["beats"]*40)))
    assert seconds <= max(1.5, move["beats"]*60/80)+1e-6


def test_after_a_pause_in_the_travel_keys_wait_for_the_note(practice_session):
    session = practice_session(bars=2)
    session.finish_listen()
    state = session.snapshot()
    target = state["teaching"]["expected_notes"][0]["pitch"]
    session.tick(1.0)
    session.command("pause")
    session.tick(10)
    session.command("resume")
    session.strike(target)              # the note is still travelling in
    assert session.tick(.1)["teaching"]["target_index"] == 0


@pytest.fixture
def piano(monkeypatch):
    names = ["Test piano"]
    monkeypatch.setattr(mido, "get_input_names", lambda: list(names))
    return names


def test_a_piano_lost_for_long_keeps_the_staff_at_the_current_target(practice_session, piano):
    session = practice_session(bars=2)
    state = free(session)
    session.strike(state["teaching"]["expected_notes"][0]["pitch"])
    session.tick(.1)
    session.reach_free_target()
    at_target = hold(session)
    piano.clear()
    session.engine.midi.port.closed = True
    session.tick(4)
    session.tick(20)                    # long enough for an old deadline to roll over
    piano.append("Test piano")
    back = session.tick(4)
    assert back["teaching"]["target_index"] == 1
    assert hold(session) == pytest.approx(at_target)


def test_choosing_a_piano_in_settings_keeps_free_going(practice_session, piano):
    session = practice_session(bars=2)
    state = free(session)
    session.strike(state["teaching"]["expected_notes"][0]["pitch"])
    session.tick(.1)
    session.ask("midi.device.select", name="Test piano")
    after = session.tick(.1)
    assert after["mode"] == "learn"
    assert after["teaching"]["phase"] == "guided_wait"
    assert after["teaching"]["target_index"] == 1


def test_tempo_percent_names_the_floor_only_when_there_is_one():
    from piano_teacher.application.practice_flow import tempo_percent
    assert tempo_percent(16, 31) == 50
    assert tempo_percent(1, 1) == 100
    assert tempo_percent(31, 60) == 52

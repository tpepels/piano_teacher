"""No piano, a piano switched on later, and a piano lost mid-take.

Owner report 2026-11-25: starting with no MIDI keyboard "just stops, but
there's no message". The learner is always told what is wrong and what to
do, and practice continues once the piano is found again.
"""
import mido
import pytest

from test_midi_journeys import play


@pytest.fixture
def unplug(monkeypatch):
    """Switch the piano off; returns a function that switches it on again."""
    def off(session):
        names = []
        monkeypatch.setattr(mido, "get_input_names", lambda: list(names))
        session.engine.midi.port.closed = True
        return lambda: names.append("Test piano")
    return off


def test_free_without_a_piano_says_so_and_continues_once_it_is_found(practice_session, unplug):
    session = practice_session(bars=2)
    plug_in = unplug(session)
    session.tick(4)
    session.finish_listen()
    waiting = session.tick(10)
    assert waiting["mode"] == "learn" and waiting["teaching"]["phase"] == "disconnected"
    assert waiting["screen"]["notice"].startswith("No piano connected.")
    assert "Settings" in waiting["screen"]["notice"]
    plug_in()
    session.tick(4)          # the next device scan finds it
    state = session.reach_free_target()
    assert state["screen"]["notice"] == ""
    target = state["teaching"]["expected_notes"]
    session.clock.at += .2
    for note in target:
        session.strike(note["pitch"])
    assert session.tick(.1)["teaching"]["target_index"] == 1


def test_a_piano_lost_in_free_keeps_the_found_notes(practice_session, unplug):
    session = practice_session(bars=2)
    session.finish_listen()
    state = session.reach_free_target()
    session.strike(state["teaching"]["expected_notes"][0]["pitch"])
    assert session.tick(.1)["teaching"]["target_index"] == 1
    plug_in = unplug(session)
    lost = session.tick(4)
    assert lost["teaching"]["phase"] == "disconnected"
    assert lost["screen"]["notice"].startswith("No piano connected.")
    plug_in()
    back = session.tick(4)
    assert back["teaching"]["phase"] == "guided_wait"
    assert back["teaching"]["target_index"] == 1


def test_a_piano_lost_in_tempo_stops_says_so_and_play_continues(practice_session, unplug):
    session = practice_session(bars=2)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert state["running"]
    plug_in = unplug(session)
    lost = session.tick(4)
    assert not lost["running"]
    assert lost["screen"]["notice"].startswith("Your piano was disconnected")
    assert "found automatically" in lost["screen"]["notice"]
    plug_in()
    back = session.tick(4)
    assert back["screen"]["notice"] == "Piano connected again: Test piano. · Press Play when you are ready."
    assert back["controls"]["primary"]["label"] == "Play" and back["controls"]["primary"]["enabled"]
    session.command(back["controls"]["primary"]["action"])
    again = session.ready_score()
    assert again["running"] and again["mode"] == "practice"
    after = play(session, again)
    assert after["running"] and after["bpm"] > again["bpm"]


def test_no_message_ever_asks_for_a_start_button(practice_session, unplug):
    session = practice_session(bars=2)
    plug_in = unplug(session)
    seen = [session.tick(4)]
    session.finish_listen()
    seen.append(session.tick(4))
    plug_in()
    seen.append(session.tick(4))
    for state in seen:
        text = " ".join(str(state.get(k) or "") for k in ("feedback", "next_action"))
        assert "Start" not in text, text

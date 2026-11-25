"""Practice never stands still without telling the learner why.

Owner report 2026-11-25: with no keyboard the app "just stops, but there's
no message". This rule is checked on EVERY state the scenarios below pass
through: the session is moving, waiting visibly for the learner (Free
shows its target, Pause shows the pause sheet), or the screen says what is
wrong or offers the control that continues.
"""
import mido
import pytest

from test_midi_journeys import play


def why_still(state):
    """'' when the state explains itself, else what is missing."""
    if not state.get("loaded"):
        return ""
    timeline = state["playback_timeline"]
    if timeline.get("state") == "failed":
        return "" if state["screen"]["notice"] else "a failed score shows no notice"
    if state["running"] or state["paused"]:
        return ""
    if state["mode"] == "listen":
        return "" if state["controls"]["primary"]["enabled"] or state["demo"] else \
            "Listen waits with no control"
    if state["mode"] == "learn":
        phase = (state.get("teaching") or {}).get("phase")
        if phase == "disconnected":
            return "" if state["screen"]["notice"].startswith("No piano connected.") else \
                "Free waits for a piano without saying so"
        if phase in ("guided_wait", "introducing", "guided_complete", "loading", None):
            return ""
        if phase == "ready":
            return "Free is ready but never starts"
        return ""
    # Stopped in Tempo: a message, or a control that continues.
    if state["screen"]["notice"] or state["controls"]["primary"]["enabled"]:
        return ""
    return "stopped in %s/%s with no message and no control" % (state["mode"], state["phase"])


@pytest.fixture
def watched(practice_session, monkeypatch):
    """Sessions whose every tick and snapshot is checked against the rule."""
    def create(**options):
        session = practice_session(**options)
        snapshot = session.snapshot

        def checked():
            state = snapshot()
            problem = why_still(state)
            assert not problem, (problem, state["mode"], state["phase"],
                                 state["screen"], state["feedback"], state["next_action"])
            return state
        session.snapshot = checked
        return session
    return create


@pytest.fixture
def piano(monkeypatch):
    """Switch the session's piano off and on."""
    class Piano:
        def __init__(self):
            self.names = ["Test piano"]
            monkeypatch.setattr(mido, "get_input_names", lambda: list(self.names))

        def off(self, session):
            self.names.clear()
            session.engine.midi.port.closed = True
            session.tick(4)

        def on(self, session):
            self.names.append("Test piano")
            session.tick(4)
    return Piano()


def test_a_whole_window_with_mistakes(watched):
    session = watched(bars=2)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    for mistake in ({"wrong": (0,)}, {"wrong": (0,)}):   # two failures: back to Free
        state = play(session, state, **mistake)
    session.finish_free()
    state = session.ready_score()
    for _ in range(3):
        state = play(session, state)


@pytest.mark.parametrize("where", ["listen", "free", "count_in", "playing"])
def test_the_piano_lost_and_found_anywhere(watched, piano, where):
    session = watched(bars=2)
    if where == "listen":
        session.start_listen()
    else:
        session.finish_listen()
        if where != "free":
            session.finish_free()
            state = session.ready_score()
            if where == "playing":
                session.clock.at = state["playback_timeline"]["current"]["deadline_ms"]/1000+.3
                session.tick()
    piano.off(session)
    session.tick(10)
    piano.on(session)
    state = session.snapshot()
    if not state["running"] and state["mode"] == "practice":
        session.command(state["controls"]["primary"]["action"])
        assert session.ready_score()["running"]


def test_starting_with_no_piano_at_all(watched, piano):
    session = watched(bars=2)
    piano.off(session)
    session.start_listen()
    session.finish_listen()
    session.tick(10)
    piano.on(session)
    session.finish_free()
    assert session.ready_score()["running"]


def test_stop_pause_and_listen_again(watched):
    session = watched(bars=2)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    session.command("pause")
    session.tick(30)
    session.command("resume")
    state = session.ready_score()
    session.command("listen")
    session.tick(1)
    session.command("ui_stop")
    session.tick(5)


def test_a_score_that_cannot_be_drawn_says_so(watched):
    session = watched(bars=2)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    for _ in range(2):
        take = session.snapshot()["playback_timeline"]["current"]
        session.ask("playback.failure", take_id=take["take_id"],
                    segment_id=take["segment_id"], reason="timeline_take_not_drawn")
    assert session.snapshot()["screen"]["notice"] == "The score stopped displaying correctly"

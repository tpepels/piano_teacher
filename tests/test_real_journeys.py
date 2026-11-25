"""Long random journeys on real pieces, including a piano that comes and
goes (owner request 2026-11-25: keep testing scenarios). Whatever happens,
the session never fails, never jams, and never stands still without saying
why."""
import random
from pathlib import Path

import mido
import pytest

from test_midi_journeys import play

PIECES = [Path(__file__).parent/"fixtures"/"pieces"/name for name in (
    "bach-invention-1.midi", "fur-elise.mxl", "gymnopedie-1.midi")]


def explained(state):
    """A stopped session either continues by itself or tells the learner."""
    if state["running"] or state["mode"] == "listen":
        return True
    if state["mode"] == "learn":
        return (state["teaching"] or {}).get("phase") != "disconnected" or \
            state["screen"]["notice"].startswith("No piano connected.")
    return bool(state["screen"]["notice"]) or state["controls"]["primary"]["enabled"]


@pytest.mark.parametrize("seed", range(3))
@pytest.mark.parametrize("source", PIECES, ids=[p.stem for p in PIECES])
def test_random_journeys_with_a_piano_that_comes_and_goes(practice_session, monkeypatch, source, seed):
    rng = random.Random(seed)
    session = practice_session(source=source.resolve())
    names = ["Test piano"]
    monkeypatch.setattr(mido, "get_input_names", lambda: list(names))
    for step in range(25):
        state = session.snapshot()
        assert state["playback_timeline"]["state"] != "failed", state["playback_timeline"]
        assert explained(state), (step, state["mode"], state["screen"], state["feedback"])
        if not names:
            # The piano is off: a few seconds later it comes back.
            session.tick(4)
            names.append("Test piano")
            session.tick(4)
            continue
        if state["mode"] == "listen":
            session.finish_listen()
            continue
        if state["mode"] == "learn":
            if rng.random() < .15:
                names.clear(); session.engine.midi.port.closed = True
                continue
            session.finish_free()
            session.ready_score()
            continue
        if not state["running"]:
            state = session.ready_score()
            if not state["running"]:
                session.command(state["controls"]["primary"]["action"])
                state = session.ready_score()
            assert state["running"], (state["feedback"], state["controls"]["primary"])
        action = rng.choice(["clean", "clean", "wrong", "missing", "late",
                             "pause", "retry", "listen", "unplug"])
        if action == "unplug":
            names.clear(); session.engine.midi.port.closed = True
            lost = session.tick(4)
            assert not lost["running"] and "disconnected" in lost["screen"]["notice"]
        elif action == "listen":
            session.command("listen")
        elif action in ("pause", "retry"):
            session.clock.at = max(session.clock.at,
                state["playback_timeline"]["current"]["deadline_ms"]/1000+.3)
            session.tick()
            if action == "retry":
                session.command("restart")
            else:
                session.command("pause")
                session.tick(rng.uniform(1, 120))
                session.command("resume")
            resumed = session.ready_score()
            assert resumed["running"] and not resumed["paused"], resumed["feedback"]
            play(session, resumed)
        else:
            play(session, state, **{
                "clean": {}, "wrong": {"wrong": (0,)}, "missing": {"missing": (0,)},
                "late": {"late": .6}}[action])

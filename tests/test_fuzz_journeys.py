"""Random journeys on real pieces, checked against rules a player notices.

Owner request 2026-11-25: go through the code for bugs and invalid
assumptions. Each step is a random but physically possible action; after
every step the rules below must hold. PIANO_TEACHER_FUZZ_SEEDS runs more
seeds locally (the suite runs a few).
"""
import math
import os
import random
from pathlib import Path

import mido
import pytest

from test_never_silent import why_still

PIECES = [Path(__file__).parent/"fixtures"/"pieces"/name for name in (
    "bach-invention-1.midi", "fur-elise.mxl", "gymnopedie-1.midi",
    "traumerei.mxl", "chopin-prelude-e-minor.mxl", "moonlight-2.mxl")]
SEEDS = range(int(os.environ.get("PIANO_TEACHER_FUZZ_SEEDS", "2")))


def timeline_world(session):
    """The published timeline's run and world now: the same pure function
    Godot's staff follows (musical_timeline.gd mirrors it)."""
    timeline = session.engine.transport.musical_timeline
    return timeline.run, timeline.world_at(session.clock.at)


class Rules:
    def __init__(self, session):
        self.session = session
        self.run, self.world, self.mastered = None, -math.inf, 0

    def check(self, state, now_ms, step):
        where = (step, state["mode"], state["phase"], state["feedback"])
        assert state["playback_timeline"]["state"] != "failed", (where, state["playback_timeline"])
        assert not why_still(state), (why_still(state), where, state["screen"])
        if state["loaded"] and state["mode"] == "practice" and state.get("target_bpm"):
            floor = max(1, round(state["target_bpm"]*.5))
            assert floor <= state["bpm"] <= state["target_bpm"], where
        assert state["lesson_steps_mastered"] >= self.mastered, where
        self.mastered = state["lesson_steps_mastered"]
        run, world = timeline_world(self.session)
        if run == self.run and world is not None:
            assert world >= self.world-1e-6, ("the staff moved backwards", where)
        if run != self.run:
            self.run = run
        if world is not None:
            self.world = world if run == self.run else -math.inf


def take_events(session, state, rng, kind):
    start = state["playback_timeline"]["current"]["deadline_ms"]/1000
    source = session.ask("score.bundle")["model"]
    floor, beat = state["play_from_beat"], 60/state["bpm"]
    events = []
    notes = [n for n in source["notes"] if n["onset_beats"] >= floor]
    for i, note in enumerate(notes):
        at = (note["onset_beats"]-floor)*beat
        pitch = note["midi_pitch"]
        if kind == "sloppy":
            at += rng.uniform(-.4, .4)
            if rng.random() < .15:
                pitch += rng.choice((-1, 1))
            if rng.random() < .1:
                continue
        elif kind == "early":
            at -= state["playback_timeline"]["current"]["count_in_beats"]*beat
        elif kind == "extra" and i == 0:
            events += [(at+.05, pitch+5, True), (at+.1, pitch+5, False)]
        events += [(at, pitch, True), (at+note["duration_beats"]*beat*.9, pitch, False)]
    if kind == "mash":
        events = [(rng.uniform(-1, 4), rng.randint(21, 108), True) for _ in range(30)]
        events += [(t+.1, p, False) for t, p, _ in events]
    sounding = source["practice_timeline"]["sounding_duration_beats"]
    return start, sorted(events, key=lambda e: (e[0], not e[2])), start+(sounding-floor)*beat+.001


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("source", PIECES, ids=[p.stem for p in PIECES])
def test_random_journeys_keep_every_rule(practice_session, monkeypatch, source, seed):
    rng = random.Random(f"{source.stem}:{seed}")
    session = practice_session(source=source.resolve())
    names = ["Test piano"]
    monkeypatch.setattr(mido, "get_input_names", lambda: list(names))
    rules = Rules(session)

    last = ["start"]

    def observe(step):
        rules.check(session.snapshot(), session.clock.at*1000, (step, last[0]))

    for step in range(40):
        observe(step)
        state = session.snapshot()
        if not names:
            session.tick(rng.uniform(1, 8))
            names.append("Test piano")
            session.tick(4)
            continue
        if rng.random() < .05:
            names.clear()
            session.engine.midi.port.closed = True
            session.tick(4)
            continue
        if state["mode"] == "listen":
            last[0] = "listen-mode"
            if rng.random() < .3:
                session.start_listen()
                observe(step)
            session.finish_listen()
            continue
        if state["mode"] == "learn":
            last[0] = "free"
            session.ready_score()      # Godot acknowledges each drawn score
            target = session.reach_free_target()
            observe(step)
            teaching = target.get("teaching") or {}
            notes = teaching.get("expected_notes") or []
            if not notes:
                session.tick(.2)
                continue
            session.clock.at += rng.uniform(.15, 2.0)
            if rng.random() < .25:     # a wrong key, a smudge or a cluster
                wrong = [notes[0]["pitch"]+rng.choice((-2, -1, 1, 2))]
                if rng.random() < .5:
                    wrong += [n["pitch"] for n in notes]
                for p in wrong:
                    session.key(p, after=0)
                for p in wrong:
                    session.key(p, False, after=0)
            else:
                for n in notes:
                    session.key(n["pitch"])
                for n in notes:
                    session.key(n["pitch"], False)
            session.tick(.1)
            if rng.random() < .05:
                session.command("pause"); session.tick(rng.uniform(1, 30)); session.command("resume")
            continue
        if not state["running"]:
            state = session.ready_score()
            if not state["running"]:
                action = state["controls"]["primary"]["action"]
                if action:
                    session.command(action)
                state = session.ready_score()
            if not state["running"]:
                session.tick(.5)
                continue
        session.ready_score()
        state = session.snapshot()
        choice = rng.choice(["clean", "clean", "sloppy", "early", "extra", "mash",
                             "silent", "pause", "restart", "listen", "stop"])
        last[0] = choice
        if choice in ("pause", "restart", "listen", "stop"):
            session.clock.at = max(session.clock.at,
                state["playback_timeline"]["current"]["deadline_ms"]/1000+rng.uniform(-2, 3))
            session.tick()
            observe(step)
            if choice == "pause":
                session.command("pause"); session.tick(rng.uniform(1, 90)); session.command("resume")
            elif choice == "restart":
                session.command("restart")
            elif choice == "listen":
                session.command("listen")
            else:
                session.command("ui_stop")
            session.tick(.05)
            continue
        start, events, end = take_events(session, state, rng,
                                         "clean" if choice == "silent" else choice)
        if choice == "silent":
            events = []
        transport = state["transport_id"]
        for at, pitch, on in events:
            session.clock.at = max(session.clock.at, start+at)
            session.engine.midi.port.send(pitch, on)
        session.clock.at = max(session.clock.at, end)
        for _ in range(5):
            session.tick(.02)
        after = session.snapshot()
        result = after.get("take_result") or {}
        if choice in ("extra", "mash", "early", "silent") and result.get("transport_id") == transport:
            assert not result.get("clean"), (choice, result)
        observe(step)

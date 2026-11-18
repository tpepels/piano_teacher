"""Every running take publishes its own source for the staff.

Regression (owner at the piano, 2026-11-18): the first Tempo take after Free
started without a published source, so the staff stayed empty for the whole
take. However a take starts, the snapshot must name that take's source and
deadline (score_queue_next), because the renderer binds only published plans.
"""
import json

import mido
import pytest

from piano_teacher import server
from piano_teacher.inprocess import EngineCommands
from piano_teacher.server import PracticeEngine


def _write_piece(path):
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(80)))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
    for pitch in (72, 74, 76, 77, 79, 77, 76, 74):
        track.append(mido.Message("note_on", note=pitch, velocity=80, time=0))
        track.append(mido.Message("note_off", note=pitch, velocity=0, time=480))
    midi.save(path)


def test_every_running_take_in_the_practice_flow_has_a_published_source(tmp_path, monkeypatch):
    music = tmp_path / "music"
    music.mkdir()
    _write_piece(music / "two_bars.mid")
    clock = [1000.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    engine.midi.port = object()  # a connected keyboard
    commands = EngineCommands(engine=engine)

    def ask(op, payload=None):
        status, body = commands.request(op, json.dumps(payload or {}))
        assert status == 0, body
        return json.loads(body)

    def press(pitch):
        for on in (True, False):
            engine._receive(mido.Message("note_on" if on else "note_off",
                                         note=pitch, velocity=80 if on else 0))

    try:
        ask("settings.update", {"music_dir": str(music),
                                "exercise_strategy": "practice-flow"})
        ask("library.open", {"id": "two_bars.mid"})
        seen = set()
        acked_audio = None
        tempo_takes = set()
        played = set()
        for _ in range(4000):
            engine.advance_clock()
            snap = ask("state.snapshot")
            mode, phase = snap.get("mode"), snap.get("phase")
            if snap.get("running") and not snap.get("paused") and \
                    mode in ("practice", "listen") and phase in ("count_in", "playing"):
                plan = snap.get("score_queue_next")
                assert isinstance(plan, dict), (mode, phase, snap.get("transport_id"))
                assert plan["transport_id"] == snap["transport_id"], (mode, phase)
                if phase == "count_in":
                    # Announced ahead, so the notes can enter from the right.
                    assert plan["deadline_at_ms"] >= engine.now() * 1000.0 - 1.0
                seen.add(mode)
                if mode == "practice":
                    tempo_takes.add(snap["transport_id"])
            if phase == "loading" and engine.awaiting_score_revision is not None:
                ask("practice.command", {"action": "score_ready",
                                         "revision": engine.awaiting_score_revision})
            demo = engine.listen.snapshot() if mode == "listen" else None
            if demo and demo.get("audio_available") and acked_audio != demo["token"]:
                acked_audio = demo["token"]
                ask("practice.command", {"action": "demo_ready", "token": demo["token"]})
            teaching = engine.teaching
            if mode == "learn" and teaching is not None and teaching._phase == "guided_wait":
                for target in list(teaching._targets[teaching._target_index]):
                    press(target["pitch"])
            if mode == "practice" and phase == "playing":
                # Play every note of the take on time so the flow advances.
                notes = engine.plan.active_variant.notes
                elapsed = engine._elapsed_beat(engine.now() - engine.visual_transport.run_at)
                for note in notes:
                    key = (snap["transport_id"], note.start)
                    if key not in played and note.start - engine.plan.active_phrase.start <= elapsed:
                        played.add(key)
                        press(note.pitch)
            if len(tempo_takes) >= 3:
                break
            clock[0] += 0.05
        assert seen == {"listen", "practice"}
        assert len(tempo_takes) >= 3, "the flow did not reach repeated Tempo takes"
    finally:
        engine.listen.cancel()
        engine.db.close()

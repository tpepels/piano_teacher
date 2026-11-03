"""Phase 6: source MIDI with a real silent bar stays on one transport axis."""
from __future__ import annotations

import json

import mido
import pytest

from piano_teacher.inprocess import EngineCommands
from piano_teacher.server import PracticeEngine
from piano_teacher import server


def write_rest_source(path):
    midi = mido.MidiFile(ticks_per_beat=480)
    meta = mido.MidiTrack([
        mido.MetaMessage("set_tempo",tempo=500000,time=0),
        mido.MetaMessage("time_signature",numerator=4,denominator=4,time=0),
    ])
    midi.tracks.append(meta)
    for channel, name, attacks in (
        (0,"Right Hand",[(0,64,480),(960,67,480),
                         (3840,69,480),(4800,72,480)]),
        (1,"Left Hand",[(0,48,960),(3840,53,960)]),
    ):
        events = []
        for onset, pitch, duration in attacks:
            events.extend([(onset,1,pitch,90),(onset+duration,0,pitch,0)])
        events.sort(key=lambda event:(event[0],event[1]))
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name",name=name,time=0))
        last_tick = 0
        for tick, on, pitch, velocity in events:
            track.append(mido.Message("note_on" if on else "note_off",
                channel=channel,note=pitch,velocity=velocity,
                time=tick-last_tick))
            last_tick = tick
        track.append(mido.MetaMessage("end_of_track",time=0))
        midi.tracks.append(track)
    midi.save(path)


def test_original_real_midi_full_rest_has_no_camera_or_grading_clock_reset(
        tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(server.time,"monotonic",lambda:clock[0])
    folder = tmp_path/"music"
    folder.mkdir()
    path = folder/"written-rest.mid"
    write_rest_source(path)
    original_bytes = path.read_bytes()
    engine = PracticeEngine(tmp_path/"engine",enable_midi=False)
    commands = EngineCommands(engine=engine)

    def ask(operation, value=None):
        code, raw = commands.request(
            operation,json.dumps(value or {}))
        assert code == 0, (operation,code,raw[:300])
        return json.loads(raw)

    try:
        assert ask("settings.update",{"music_dir":str(folder)})["music_dir"] == str(folder)
        opened = ask("library.open",{"id":path.name})
        assert opened["loaded"] and opened["piece_last_bar"] >= 3
        # Select the untouched original entire MIDI, including both hands
        # and its authentic four-quarter-beat silent middle measure.
        selected = ask("practice.command",{"action":"perform","scope":"whole"})
        assert selected["mode"] == "perform"
        model = ask("score.semantic")
        assert model["revision"] == selected["revision"]
        assert model["duration_beats"] >= 12
        attacks = [event for event in model["notation_events"]
            if event.get("kind")=="note" and event.get("is_attack")]
        rests = [event for event in model["notation_events"]
            if event.get("kind")=="rest"]
        assert any(float(event["beat"]) < 4 for event in attacks)
        assert not any(4-1e-6 <= float(event["beat"]) < 8-1e-6
            for event in attacks)
        assert any(4-1e-6 <= float(event.get("beat",-1)) < 8-1e-6
            for event in rests)
        assert any(float(event["beat"]) >= 8 for event in attacks)
        started = ask("practice.command",{
            "action":"score_ready","revision":selected["revision"]})
        if not started["running"]:
            started = ask("practice.command",{"action":"start"})
        assert started["running"] and started["preview_only"]
        transport_id = started["transport_id"]
        downbeat = engine.run_at
        tempo = engine._active_tempo_map()
        samples = []
        for beat in (3.8,4.0,5.0,6.0,7.8,8.0,8.2,9.0):
            clock[0] = downbeat + tempo.seconds_at(beat)
            state = ask("state.snapshot")
            assert state["transport_id"] == transport_id
            assert state["revision"] == model["revision"]
            assert state["phase"] == "playing"
            assert state["visual_scroll_beat"] == pytest.approx(beat,abs=.015)
            assert state["visual_scroll_speed"] > 0
            assert state["clock_beat"] == pytest.approx(beat,abs=.015)
            assert state["mastered"] == 0
            samples.append(state["visual_scroll_beat"])
        assert all(a < b for a,b in zip(samples,samples[1:]))
        assert path.read_bytes() == original_bytes
    finally:
        engine.db.close()

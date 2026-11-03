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
        # The unmodified original normally has a constant-tempo policy.
        # Generated shaped stages supply a TempoMap; both share source beats.
        seconds_at = (tempo.seconds_at if tempo is not None
                      else lambda beat: beat * 60.0 / float(started["bpm"]))
        samples = []
        for beat in (3.8,4.0,5.0,6.0,7.8,8.0,8.2,9.0):
            clock[0] = downbeat + seconds_at(beat)
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


def test_entire_real_midi_performance_uses_callback_grading_and_saved_review(
        tmp_path, monkeypatch):
    """Actual MIDI note messages enter the locked engine; no fake assessment.

    A full written rest must survive the grading path, including repeats and
    one deliberately wrong pitch on the following measure. Hardware latency
    is deliberately not asserted by this software clock fixture.
    """
    clock = [2000.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    folder = tmp_path/"music"
    folder.mkdir()
    path = folder/"graded-rest.mid"
    write_rest_source(path)
    original = path.read_bytes()
    engine = PracticeEngine(tmp_path/"grading", enable_midi=False)
    engine.midi.port = object()  # A connected software port; callbacks are real.
    commands = EngineCommands(engine=engine)

    def ask(op, payload=None):
        status, body = commands.request(op, json.dumps(payload or {}))
        assert status == 0, (op, status, body[:400])
        return json.loads(body)

    def send_original(*, wrong_pitch=False):
        phrase = engine.plan.active_phrase
        tempo = engine._active_tempo_map()
        bpm = engine.plan.bpm
        origin = engine.run_at
        offset = phrase.start
        notes = [n for n in phrase.notes if engine.plan.hand == "both" or
                 n.hand == engine.plan.hand]
        assert len(notes) >= 6
        changed_note = next(n for n in notes if n.start-offset >= 8
                            and n.hand == "right")
        def relative(at):
            return (tempo.seconds_at(at-offset) if tempo is not None
                    else (at-offset)*60.0/bpm)

        events = []
        for note in notes:
            pitch = note.pitch+1 if wrong_pitch and note is changed_note else note.pitch
            channel = 0 if note.hand == "right" else 1
            events.append((relative(note.start), 1, pitch, channel))
            events.append((relative(note.end), 0, pitch, channel))
        events.sort(key=lambda item:(item[0],item[1],item[2]))
        before = engine.midi.input_count
        for seconds, on, pitch, channel in events:
            clock[0] = origin+seconds
            message = mido.Message("note_on" if on else "note_off",
                                   note=pitch, velocity=86 if on else 0,
                                   channel=channel)
            engine._receive(message)
            if 4 < seconds*bpm/60 < 8:
                pytest.fail("Fixture unexpectedly contains MIDI within the written rest")
        assert engine.midi.input_count-before == len(notes)
        last_beat = phrase.end-phrase.start
        last_seconds = (tempo.seconds_at(last_beat) if tempo is not None
                        else last_beat*60.0/bpm)
        clock[0] = origin+last_seconds+0.6
        final = ask("state.snapshot")
        assert not final["running"] and not final["preview_only"]
        assert engine.performance_summary is not None
        return final, engine.performance_summary, changed_note

    try:
        ask("settings.update",{"music_dir":str(folder),
                               "exercise_strategy":"coda-fukuda-midi"})
        opened = ask("library.open",{"id":path.name})
        assert opened["loaded"]
        ready = ask("practice.command",{"action":"perform","scope":"whole"})
        revision = ready["revision"]
        model = ask("score.semantic")
        assert model["revision"] == revision and len(model["notes"]) >= 6
        started = ask("practice.command",{"action":"score_ready",
                                          "revision":revision})
        if not started["running"]:
            started = ask("practice.command",{"action":"start"})
        assert started["running"] and not started["preview_only"]
        first_transport = started["transport_id"]
        clean, clean_review, _ = send_original()
        assert clean["transport_id"] == first_transport
        assert clean_review["correct"] == clean_review["total"]
        assert clean_review["total"] >= 6
        assert clean_review["wrong"] == clean_review["missed"] == 0
        assert not clean_review["weakest_bars"]
        assert not clean["feedback_unmapped"]
        assert path.read_bytes() == original

        restarted = ask("practice.command",{"action":"start"})
        assert restarted["transport_id"] > first_transport
        assert restarted["revision"] == revision
        broken, review, changed = send_original(wrong_pitch=True)
        assert review["correct"] < review["total"]
        assert review["wrong"] >= 1
        assert review["weakest_bars"]
        assert any(mark["source_id"] == changed.source_id
                   and mark["status"] == "wrong"
                   for mark in engine.feedback_marks)
        assert broken["revision"] == revision
        assert path.read_bytes() == original
    finally:
        engine.listen.cancel()
        engine.db.close()

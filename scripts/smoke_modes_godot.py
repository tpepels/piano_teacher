#!/usr/bin/env python3
"""Real desktop Listen PCM playback and uninterrupted Perform learner journey.

Physical MIDI discovery/opening alone uses a test adapter. Godot downloads the
real synthesized WAV, plays a real AudioStreamWAV, renders ordinary score motion
and uses visible controls. Software audio evidence is not speaker acceptance.
"""
from __future__ import annotations

import argparse
from array import array
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from unittest.mock import patch
from urllib.request import urlopen
import wave

import mido

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from piano_teacher.server import Handler, PracticeEngine, ThreadingHTTPServer
from scripts.smoke_teaching_godot import PIANO, TestMidiInput


def make_fixture(path: Path) -> None:
    """Four arbitrary user bars with an opening rest and a held final chord."""
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("set_tempo", tempo=500000, time=0),
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
        mido.MetaMessage("end_of_track", time=7680),
    ]))
    track = mido.MidiTrack([mido.MetaMessage("track_name", name="Right Hand", time=0)])
    events = []
    for beat in (1,2,3,4,5,6,8,9,10,11,12,13,14):
        pitch = (72,74,76,77)[beat % 4]
        duration = 2 if beat == 14 else 1 if beat >= 10 else .5
        for chord_pitch in (pitch-5,pitch):
            events.extend(((beat*480,1,chord_pitch), (int((beat+duration)*480),0,chord_pitch)))
    previous = 0
    for tick,down,pitch in sorted(events):
        track.append(mido.Message("note_on" if down else "note_off",note=pitch,
            velocity=85 if down else 0,time=tick-previous))
        previous = tick
    track.append(mido.MetaMessage("end_of_track",time=7680-previous))
    midi.tracks.append(track)
    midi.save(path)


def inspect_wav(raw: bytes) -> dict:
    with wave.open(BytesIO(raw), "rb") as audio:
        assert audio.getsampwidth() == 2, "Demo must contain actual signed 16-bit PCM"
        rate,channels,frames = audio.getframerate(),audio.getnchannels(),audio.getnframes()
        pcm = array("h",audio.readframes(frames))
        if sys.byteorder != "little":
            pcm.byteswap()
    assert frames/rate >= 4, "Full four-bar ending must not be clipped"
    assert max(abs(v) for v in pcm) > 100, "Demo PCM must contain actual note synthesis"
    assert all(v == 0 for v in pcm[:int(rate*channels*.2)]), "Source opening rest must remain silent"
    rest = pcm[int(rate*channels*1.78):int(rate*channels*1.95)]
    assert all(v == 0 for v in rest), "Source internal rest must remain silent"
    ending = pcm[int(rate*channels*3.6):int(rate*channels*3.85)]
    assert sum(v != 0 for v in ending) > rate*channels*.05, "Held final note must survive near phrase end"
    return {"frames":frames,"rate":rate,"channels":channels,"duration_seconds":frames/rate,
            "peak":max(abs(v) for v in pcm),"nonzero_samples":sum(v != 0 for v in pcm)}


def run(output: Path, resolution: tuple[int, int] = (1536, 960)) -> dict:
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        raise RuntimeError("Godot 4 is required")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError("A graphical desktop is required for actual rendered mode evidence")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1",8765)) == 0:
            raise RuntimeError("Port 8765 is occupied; close Piano Teacher first")
    output = output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    runtime = output/f"runtime-{time.time_ns()}"
    runtime.mkdir()
    music = output/"user-music"
    music.mkdir(exist_ok=True)
    source = music/"Imported rest and held ending.mid"
    make_fixture(source)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    for key,directory in (("XDG_DATA_HOME","data"),("XDG_CONFIG_HOME","config"),("XDG_CACHE_HOME","cache")):
        env[key] = str(runtime/directory)
    engine = PracticeEngine(runtime/"backend-data",enable_midi=True)
    engine.library.update(fullscreen=False)
    adapter = TestMidiInput()
    server = ThreadingHTTPServer(("127.0.0.1",8765),Handler)
    Handler.engine = engine
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    desktop = None
    transcript = output/"godot.log"
    journal = []

    def log(event, **details):
        journal.append({"event":event,"at":time.monotonic(),**details})
        (output/"journey.json").write_text(json.dumps(journal,indent=2))
        print("MODES_LEARNER:",event,details,flush=True)

    def until(predicate,label,timeout=25):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            text = transcript.read_text(errors="replace") if transcript.exists() else ""
            if any(token in text for token in ("SCRIPT ERROR","ERROR:","MODES_FAIL:")):
                raise RuntimeError(f"Mode UI failed while waiting for {label}:\n{text}")
            if desktop is not None and desktop.poll() is not None:
                raise RuntimeError(f"Godot exited while waiting for {label}:\n{text}")
            result = predicate(text)
            if result:
                return result
            time.sleep(.01)
        raise RuntimeError(f"Timed out: {label}\n{text}")

    try:
        with patch("mido.get_input_names",return_value=[PIANO]), patch("mido.open_input",adapter.open):
            thread.start()
            with transcript.open("w") as ui_log:
                desktop = subprocess.Popen([godot,"--path",str(ROOT/"godot"),"--resolution",f"{resolution[0]}x{resolution[1]}",
                    "--audio-driver","Dummy","--script",str(ROOT/"tests/godot/modes_journey.gd"),
                    "--",str(output),str(music),str(resolution[0]),str(resolution[1])],cwd=ROOT,env=env,stdout=ui_log,stderr=subprocess.STDOUT)
                until(lambda text: "MODES_STAGE:import-ready" in text,"normal user MIDI import")
                initial = engine.state()
                assert "demo" in initial, "Listen demo contract is required"
                assert initial["bpm"] == initial["target_bpm"] == 240
                identity = engine.plan.identity
                assert engine.plan.exercise.kind == "connect"
                assert (engine.plan.active_phrase.first_bar, engine.plan.active_phrase.last_bar) == (1, 4)
                assert (initial["first_bar"], initial["last_bar"]) == (1, 2)
                assert initial["learner"]["total_units"] == 2 and initial["mastered"] == 0
                assert initial["lesson_level"] == "original" and len(engine.plan.active_variant.notes) == 26
                until(lambda text: "MODES_STAGE:audio-playing" in text,"real AudioStreamWAV playback")
                listening = engine.state()
                assert listening["mode"] == "listen" and listening["running"]
                assert listening["required_notes"] == 26 and listening["duration_beats"] == 16
                assert engine.recorder is None and engine.pending_result is None
                assert listening["mastered"] == listening["streak"] == 0
                demo = listening["demo"]
                assert demo["stage_key"] == identity
                assert demo["source_ids"] == [f"{identity}:{index}" for index in engine.plan.active_variant.source_indices]
                assert len(demo["source_ids"]) == 26
                assert demo["ready"] and demo["token"] and demo["url"].startswith("/demo.wav?token=")
                with urlopen("http://127.0.0.1:8765"+demo["url"],timeout=15) as response:
                    raw = response.read()
                (output/"downloaded-demo.wav").write_bytes(raw)
                wav = inspect_wav(raw)
                assert abs(wav["duration_seconds"]-demo["duration_seconds"]) < .1
                log("Listen downloads nonzero PCM with source opening rest and held ending",**wav)
                # Playing along with an example is real MIDI input, but it is not an assessed take.
                for pitch in (72,74,76):
                    adapter.send(pitch)
                    adapter.send(pitch,False)
                after_input = engine.state()
                assert engine.recorder is None and after_input["midi_notes"] == 0
                assert after_input["mastered"] == after_input["streak"] == 0
                log("Listen MIDI never creates a recorder or clean credit",input_events=6)
                until(lambda text: "MODES_STAGE:perform-playing" in text,"normal Perform mode selection")
                start = engine.state()
                assert start["mode"] == "perform" and start["running"] and start["bpm"] == 240
                assert not start["preview_only"] and start["required_notes"] == 26
                perform_id = start["transport_id"]
                last_beat = start["clock_beat"]
                while True:
                    state = engine.state()
                    if state["phase"] == "performance_complete":
                        break
                    assert state["mode"] == "perform" and state["running"], state
                    assert state["phase"] in ("playing","count_in")
                    assert state["transport_id"] == perform_id and state["bpm"] == 240
                    assert state["clock_beat"] >= last_beat-.05
                    assert state["recovery_beat"] is None and not state["guided_recovery"]
                    last_beat = state["clock_beat"]
                    until(lambda text: True,"live performance")
                    time.sleep(.005)
                summary = state["performance_summary"]
                assert summary["accuracy_percent"] == 0 and summary["correct"] == 0 and summary["total"] == summary["missed"] == 26
                assert summary["missed_pitches"] == [67,69,71,72,74,76,77] and summary["early"] == summary["late"] == 0
                assert summary["extra_notes"] == 0 and summary["weakest_bars"]
                weak = summary["weakest_bars"][0]
                assert weak["errors"] >= 5 and weak["first_bar"] == 3 and weak["last_bar"] == 4
                assert weak["start_beat"] == 8 and weak["end_beat"] == 16
                assert state["mastered"] == state["streak"] == 0 and engine.pending_result is None
                log("All missed Perform reaches its natural endpoint without slowdown or rewind",summary=summary)
                until(lambda text: "MODES_STAGE:weak-practice-playing" in text,"visible practice weakest-section action")
                practice = engine.state()
                assert practice["mode"] == "practice" and practice["running"]
                assert practice["play_from_beat"] == weak["start_beat"] and practice["bpm"] == 240
                assert practice["mastered"] == practice["streak"] == 0 and engine.plan.identity == identity
                log("Weakest source chunk opens real Practice",retry_range=practice.get("retry_range"))
                desktop.wait(timeout=15)
                text = transcript.read_text(errors="replace")
                if desktop.returncode or "MODES_RESULT:PASS" not in text or any(
                    token in text for token in ("SCRIPT ERROR","ERROR:","MODES_FAIL:")):
                    raise RuntimeError(f"Mode journey failed ({desktop.returncode}):\n{text}")
                result = json.loads((output/"result.json").read_text())
                assert result["failures"] == []
                result["wav"] = wav
                result["performance_summary"] = summary
                (output/"result.json").write_text(json.dumps(result,indent=2))
                print(f"MODES JOURNEY PASSED: {len(result['frames'])} real frames; {output}",flush=True)
                return result
    finally:
        if desktop is not None and desktop.poll() is None:
            desktop.terminate()
            try:
                desktop.wait(timeout=5)
            except subprocess.TimeoutExpired:
                desktop.kill()
                desktop.wait(timeout=5)
        if thread.is_alive():
            server.shutdown()
            thread.join(timeout=5)
        server.server_close()
        engine.connect("")
        engine.db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=Path("/tmp/piano-teaching-p3"))
    parser.add_argument("--resolution",default="1536x960",help="Desktop window WIDTHxHEIGHT")
    options = parser.parse_args()
    try:
        resolution = tuple(map(int,options.resolution.lower().split("x")))
        if len(resolution) != 2 or min(resolution) < 480:
            raise ValueError("Resolution must be WIDTHxHEIGHT, at least480 pixels each")
        run(options.output_dir,resolution)
    except Exception as error:
        traceback.print_exc()
        print(f"MODES JOURNEY FAILED: {error}",file=sys.stderr)
        raise SystemExit(1)

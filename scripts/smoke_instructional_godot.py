#!/usr/bin/env python3
"""A real desktop learner: notes -> musical retry -> key help -> honest mastery.

Only physical MIDI discovery/opening is replaced. Every played attack/release
passes through PracticeEngine._receive at real monotonic time. Godot uses its
normal controls, HTTP polling, renderer and score projection. No forced phases,
clock rewrites, assessment-array injection or answer-submission API is used.
"""
from __future__ import annotations

import argparse
import json
from array import array
from io import BytesIO
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from urllib.request import urlopen
import wave
from unittest.mock import patch

import mido

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from piano_teacher.server import Handler, PracticeEngine, ThreadingHTTPServer
from scripts.smoke_teaching_godot import PIANO, TestMidiInput


def make_fixture(path: Path) -> None:
    """Two 8/4 source measures: eight onsets and optional inner chord notes.

    The default two-measure course contains the whole passage. Seeking to
    measure 2 gives a five-attack partial retry without changing recovery
    thresholds or using the opt-in legacy consolidated course.
    """
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("set_tempo", tempo=500000, time=0),
        mido.MetaMessage("time_signature", numerator=8, denominator=4, time=0),
        mido.MetaMessage("end_of_track", time=7680),
    ]))
    track = mido.MidiTrack([mido.MetaMessage("track_name", name="Right Hand", time=0)])
    events = []
    for beat in (0, 1, 4, 8, 9, 11, 13, 15):
        upper = (72, 74, 76, 77)[beat % 4]
        for pitch in (upper - 5, upper):
            events.extend(((beat * 480, 1, pitch), (beat * 480 + 240, 0, pitch)))
    previous = 0
    for tick, down, pitch in sorted(events):
        track.append(mido.Message("note_on" if down else "note_off", note=pitch,
            velocity=88 if down else 0, time=tick - previous))
        previous = tick
    track.append(mido.MetaMessage("end_of_track", time=7680-previous))
    midi.tracks.append(track)
    midi.save(path)


def run(output: Path, *, finish_modes: bool = False) -> dict:
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        raise RuntimeError("Godot 4 is required")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError("A graphical session is required for rendered learner evidence")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8765)) == 0:
            raise RuntimeError("Port 8765 is occupied; close Piano Teacher first")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    runtime = output / f"runtime-{time.time_ns()}"
    runtime.mkdir()
    music = output / "user-music"
    music.mkdir(exist_ok=True)
    source = music / "Imported two-measure lesson.mid"
    make_fixture(source)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    for name, directory in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"),
                            ("XDG_CACHE_HOME", "cache")):
        environment[name] = str(runtime / directory)
    engine = PracticeEngine(runtime / "backend-data", enable_midi=True)
    engine.library.update(fullscreen=False)
    adapter = TestMidiInput()
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    Handler.engine = engine
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    desktop = None
    transcript = output / "godot.log"
    journal = []
    midi_events = []
    begun = time.monotonic()

    def log(event, **details):
        journal.append({"event": event, "at": time.monotonic(), **details})
        (output / "journey.json").write_text(json.dumps(journal, indent=2))
        print("INSTRUCTIONAL_LEARNER:", event, details, flush=True)

    def send(pitch, down=True):
        before = engine.state()
        at = time.monotonic()
        adapter.send(pitch, down)
        midi_events.append({"at": at, "pitch": pitch, "down": down,
            "transport_id": before["transport_id"], "mode": before["mode"],
            "phase": before["phase"], "bpm": before.get("bpm"),
            "from_beat": before.get("play_from_beat"), "clock_beat": before.get("clock_beat")})

    def content():
        text = transcript.read_text(errors="replace") if transcript.exists() else ""
        if any(token in text for token in ("SCRIPT ERROR", "ERROR:", "INSTRUCTIONAL_FAIL:")):
            raise RuntimeError(f"Godot learner failure:\n{text}")
        return text

    def until(predicate, label, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = content()
            if desktop is not None and desktop.poll() is not None:
                raise RuntimeError(f"Godot exited while waiting for {label}:\n{text}")
            value = predicate(text)
            if value:
                return value
            time.sleep(.01)
        raise RuntimeError(f"Timed out: {label}\n{content()}")

    def solve_guided(label):
        solved = []
        while engine.state()["phase"] == "guided_wait":
            state = engine.state()
            targets = state["teaching"]["expected_notes"]
            assert targets, "Guided mode must expose actual source targets"
            with engine.lock:
                identities = {f"{engine.plan.identity}:{i}": n for i, n in
                    zip(engine.plan.active_variant.source_indices, engine.plan.active_variant.notes)}
            for note in targets:
                source_note = identities[note["id"]]
                assert note["pitch"] == source_note.pitch and note["source_beat"] == source_note.start
                send(note["pitch"])
            completed = engine.state()
            assert completed["teaching"]["target_index"] == state["teaching"]["target_index"] + 1
            for note in targets:
                send(note["pitch"], False)
                solved.append(note["id"])
            if completed["phase"] == "guided_complete":
                assert completed["streak"] == completed["mastered"] == 0
                assert not completed["teaching"]["mastery_eligible"]
                log(label, solved=len(solved), bpm=completed["bpm"], fragment=completed["teaching"]["fragment"])
                return
            time.sleep(.06)
        raise AssertionError(f"Guided learner unexpectedly left waiting: {engine.state()}")

    try:
        with patch("mido.get_input_names", return_value=[PIANO]), patch("mido.open_input", adapter.open):
            thread.start()
            with transcript.open("w") as ui_log:
                desktop = subprocess.Popen([godot, "--path", str(ROOT / "godot"),
                    "--resolution", "1536x960", "--audio-driver", "Dummy", "--script",
                    str(ROOT / "tests/godot/instructional_journey.gd"), "--", str(output), str(music),
                    "1" if finish_modes else "0"],
                    cwd=ROOT, env=environment, stdout=ui_log, stderr=subprocess.STDOUT)
                until(lambda text: "INSTRUCTIONAL_STAGE:wrong-ready" in text, "normal UI import and tempo selection")
                initial = engine.state()
                assert {"next_action", "transition_in_seconds", "retry_range", "guided_recovery"} <= initial.keys(), \
                    "Instructional transition contract is required"
                assert engine.source == str(source.resolve())
                assert initial["bpm"] == initial["target_bpm"] == 240
                assert initial["lesson_level"] == "skeleton" and initial["teaching"]["target_count"] == 8
                assert (initial["first_bar"], initial["last_bar"]) == (1, 2)
                assert engine.plan.piece.bar_boundaries == (0, 8, 16)
                assert "learner" in initial, "Stateful learner course contract is required"
                assert initial["learner"]["total_units"] == 1 and initial["learner"]["prepared_units"] == 0
                identity = engine.plan.identity
                send(61)
                wrong = engine.state()
                assert wrong["teaching"]["hint_visible"] and wrong["teaching"]["target_index"] == 0
                log("wrong guided note reveals hint without advancing")
                until(lambda text: "INSTRUCTIONAL_STAGE:hint-rendered" in text, "real hinted keyboard")
                send(61, False)
                solve_guided("opening guided fragment completed without mastery")
                prepared = engine.state()["learner"]
                assert prepared["prepared_units"] == prepared["total_units"] == 1
                until(lambda text: "INSTRUCTIONAL_STAGE:partial-timed-ready" in text,
                      "visible paused source-measure control selects a temporary partial")
                assert engine.open_from_beat == 0, "Later full attempts must retain the passage beginning"
                assert engine.state()["mastered"] == engine.state()["streak"] == 0
                attempt = 0
                current_id = None
                scheduled = []
                last_phase = None
                recovery_solved = False
                next_variant = False
                prepared_all = True
                listened = False
                summary = None
                revisited = False
                earned_variant = None
                perform_transport = None
                perform_beat = -100.0
                full_clean_tempos = []
                deadline = time.monotonic() + 160
                while time.monotonic() < deadline:
                    text = content()
                    if desktop.poll() is not None:
                        break
                    state = engine.state()
                    if state.get("mastered", 0) == 1 and not next_variant:
                        assert attempt == 9, f"Mastery arrived after unexpected attempt {attempt}"
                        assert state["lesson_level"] == "original" and engine.plan.identity != identity
                        next_variant = True
                        assert state["mode"] == "learn" and len(engine.plan.active_variant.notes) == 16
                        assert state["target_bpm"] == 240 and state["streak"] == 0
                        earned_variant = {"mode":state["mode"],"level":state["lesson_level"],
                            "source_notes":len(engine.plan.active_variant.notes),"mastered":state["mastered"]}
                        log("three clean target-speed takes unlock actual original variant in Learn", attempt=attempt)
                        if not finish_modes:
                            desktop.wait(timeout=15)
                            break
                    if next_variant:
                        assert state["mastered"] == 1 and state["streak"] == 0
                        if state["mode"] == "listen" and state["running"] and not listened:
                            assert state["bpm"] == state["target_bpm"] == 240 and state["required_notes"] == 16
                            assert engine.recorder is None and state["midi_notes"] == 0
                            demo = state["demo"]
                            assert demo["source_ids"] == [f"{engine.plan.identity}:{index}" for index in engine.plan.active_variant.source_indices]
                            with urlopen("http://127.0.0.1:8765"+demo["url"],timeout=15) as response:
                                raw = response.read()
                            (output/"earned-original-demo.wav").write_bytes(raw)
                            with wave.open(BytesIO(raw),"rb") as audio:
                                assert audio.getsampwidth() == 2 and audio.getnframes()/audio.getframerate() >= 4
                                pcm = array("h",audio.readframes(audio.getnframes()))
                            if sys.byteorder != "little":
                                pcm.byteswap()
                            assert max(abs(value) for value in pcm) > 100
                            listened = True
                            log("same earned original source has real Listen PCM without mastery", source_notes=16)
                        if state["mode"] == "perform" and state["running"]:
                            assert listened and state["bpm"] == 240 and state["target_bpm"] == 240
                            if perform_transport is None:
                                perform_transport = state["transport_id"]
                            assert state["transport_id"] == perform_transport
                            assert state["clock_beat"] >= perform_beat-.05 and state["recovery_beat"] is None
                            perform_beat = state["clock_beat"]
                        if state["phase"] == "performance_complete" and summary is None:
                            summary = state["performance_summary"]
                            assert summary["correct"] == 0 and summary["total"] == 16 and summary["accuracy_percent"] == 0
                            assert summary["missed"] == 16 and state["learner"]["trouble_units"]
                            log("same original Perform finishes all misses and saves source trouble", summary=summary)
                        if summary is not None and state["mode"] == "learn" and state["phase"] == "guided_wait":
                            assert state["teaching"]["fragment"]["start_beat"] == 0
                            assert state["teaching"]["fragment"]["first_bar"] == 1
                            assert len(state["teaching"]["expected_notes"]) == 2
                            revisited = True
                            if not any(entry["event"] == "saved source trouble revisited without false mastery" for entry in journal):
                                log("saved source trouble revisited without false mastery")
                        time.sleep(.003)
                        continue
                    if state["mode"] == "learn" and state.get("guided_recovery") \
                            and state["phase"] == "guided_wait" and not recovery_solved:
                        assert attempt == 2 and state["first_bar"] == state["last_bar"] == 2
                        assert state["bpm"] == 194 and state["target_bpm"] == 240
                        until(lambda text: "INSTRUCTIONAL_STAGE:recovery-guided-ready" in text, "static exact failed fragment")
                        solve_guided("failed bars guided correctly without mastery")
                        recovery_solved = True
                        scheduled = []
                        continue
                    if state.get("running") and state["transport_id"] != current_id:
                        attempt += 1
                        current_id = state["transport_id"]
                        offset = state["play_from_beat"]
                        expected_tempos = (240, 216, 194, 194, 207, 223, 240, 240, 240)
                        assert attempt <= len(expected_tempos), "Unexpected extra attempt"
                        assert state["bpm"] == expected_tempos[attempt-1], (attempt, state)
                        assert offset == (8 if attempt in (1, 2, 3) else 0), (attempt, offset)
                        assert state["target_bpm"] == 240 and engine.plan.identity == identity
                        assert state["mastered"] == 0 and state["streak"] == max(0, attempt-7)
                        with engine.lock:
                            phrase = engine.plan.active_phrase
                            required = [n for n in phrase.notes if n.start >= phrase.start+offset-1e-7]
                            assert len(phrase.notes) == 8 and phrase.end-phrase.start == 16
                            seconds = 60 / engine.plan.bpm
                            epoch = engine.run_at
                        scheduled = []
                        for note in required:
                            local = note.start - phrase.start
                            if attempt in (1, 2):
                                continue
                            scheduled.extend(((epoch+(local-offset)*seconds+.002, note.pitch, True),
                                (epoch+(min(note.end,phrase.end)-phrase.start-offset)*seconds+.002, note.pitch, False)))
                        scheduled.sort()
                        log("musical attempt begins", attempt=attempt, transport_id=current_id,
                            bpm=state["bpm"], target=240, from_beat=offset,
                            attacks=len(scheduled)//2, streak=state["streak"])
                    if state.get("running") and not state.get("paused"):
                        now = time.monotonic()
                        while scheduled and scheduled[0][0] <= now:
                            at, pitch, down = scheduled.pop(0)
                            assert now-at < .07, f"MIDI driver scheduling stalled by {now-at:.3f}s"
                            send(pitch, down)
                    phase_key = (state["transport_id"], state["phase"], state.get("pause_context"))
                    if phase_key != last_phase:
                        last_phase = phase_key
                        if state["phase"] in ("feedback", "recovering", "paused", "loading"):
                            log("instructional phase", attempt=attempt, phase=state["phase"],
                                bpm=state.get("bpm"), next_action=state.get("next_action"),
                                transition=state.get("transition_in_seconds"), retry_range=state.get("retry_range"),
                                guided=state.get("guided_recovery"), streak=state.get("streak"))
                        if state["phase"] in ("feedback", "recovering"):
                            assert state["mastered"] == 0
                            if attempt in (1, 2):
                                assert state["retry_range"] == {"first_bar":2,"last_bar":2,"start_beat":8,"end_beat":16}
                                assert state["bpm"] == (216 if attempt == 1 else 194)
                                assert bool(state["guided_recovery"]) == (attempt == 2)
                            elif attempt == 3:
                                assert state["streak"] == 0 and "whole passage" in state["next_action"].lower()
                                partial = state["performance_summary"]
                                assert partial["correct"] == partial["total"] == 5
                                assert partial["missed"] == partial["extra_notes"] == 0
                                assert partial["accuracy_percent"] == 100 and engine.pending_result is None
                            elif attempt >= 4:
                                assert engine.pending_result is not None and engine.pending_result.clean, \
                                    f"Timestamped MIDI attempt {attempt} was not clean: {state}"
                                full_clean_tempos.append(state["bpm"])
                    time.sleep(.003)
                else:
                    raise RuntimeError("Whole learner journey exceeded 160 seconds")
                text = content()
                if desktop.returncode or "INSTRUCTIONAL_RESULT:PASS" not in text:
                    raise RuntimeError(f"Instructional desktop failed ({desktop.returncode}):\n{text}")
                assert next_variant and recovery_solved and prepared_all and attempt == 9
                if finish_modes:
                    assert listened and summary is not None and revisited
                assert full_clean_tempos == [194, 207, 223, 240, 240, 240]
                result = json.loads((output / "result.json").read_text())
                assert result["failures"] == []
                result["elapsed_seconds"] = time.monotonic()-begun
                result["full_clean_tempos"] = full_clean_tempos
                result["earned_variant"] = earned_variant
                result["finished_modes"] = finish_modes
                result["revisited_trouble"] = revisited
                result["performance_summary"] = summary
                (output / "result.json").write_text(json.dumps(result, indent=2))
                print(f"INSTRUCTIONAL JOURNEY PASSED: {len(result['frames'])} frames, "
                      f"{result['elapsed_seconds']:.1f}s; {output}", flush=True)
                return result
    finally:
        (output / "midi.json").write_text(json.dumps(midi_events, indent=2))
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
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/piano-teaching-p2"))
    parser.add_argument("--finish-modes",action="store_true",help="Continue the earned stage through Listen, Perform and saved trouble")
    options = parser.parse_args()
    try:
        run(options.output_dir,finish_modes=options.finish_modes)
    except Exception as error:
        traceback.print_exc()
        print(f"INSTRUCTIONAL JOURNEY FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)

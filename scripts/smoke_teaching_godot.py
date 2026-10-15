#!/usr/bin/env python3
"""Real desktop journey: user MIDI import -> guided hints -> timed practice.

The test adapter replaces only physical MIDI discovery/opening. MIDI messages
enter the production callback; Godot uses ordinary HTTP and visible controls.
No production endpoint accepts injected learner answers. Rendered PNGs and logs
are retained. This requires a graphical session and exclusive port 8765.
"""
from __future__ import annotations

import argparse
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

import mido

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from piano_teacher.server import Handler, PracticeEngine, ThreadingHTTPServer

PIANO = "Journey test piano"


def make_fixture(path: Path) -> None:
    """Two user-imported bars; repeated two-hand attacks survive skeletonization."""
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("set_tempo", tempo=500000, time=0),
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
        mido.MetaMessage("end_of_track", time=3840),
    ]))
    for channel, name, chords in (
        (0, "Right Hand", ((64, 67), (64, 67), (65, 69), (65, 69))),
        (1, "Left Hand", ((48,), (48,), (50,), (50,))),
    ):
        track = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0)])
        events = []
        for beat, chord in zip((0, 1, 4, 5), chords):
            for pitch in chord:
                events.extend(((beat * 480, 1, pitch), (beat * 480 + 240, 0, pitch)))
        last = 0
        for tick, down, pitch in sorted(events):
            track.append(mido.Message("note_on" if down else "note_off", channel=channel,
                note=pitch, velocity=84 if down else 0, time=tick - last))
            last = tick
        track.append(mido.MetaMessage("end_of_track", time=3840-last))
        midi.tracks.append(track)
    midi.save(path)


class TestMidiInput:
    """Physical input boundary only; callback and timestamping remain production."""
    closed = False

    def __init__(self):
        self.callback = None

    def open(self, name, *, callback):
        if name != PIANO:
            raise ValueError(f"Unknown test input {name}")
        self.closed = False
        self.callback = callback
        return self

    def close(self):
        self.closed = True

    def send(self, pitch: int, down: bool = True):
        if self.callback is None or self.closed:
            raise RuntimeError("The UI has not connected the MIDI input")
        self.callback(mido.Message("note_on" if down else "note_off", note=pitch,
                                   velocity=84 if down else 0))


def run(output: Path, resolution: tuple[int, int] = (1536, 960)) -> dict:
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        raise RuntimeError("Godot 4 is required")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError("A graphical session is required for actual rendered frames")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8765)) == 0:
            raise RuntimeError("Port 8765 is occupied; close Piano Teacher first")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    music = output / "user-music"
    music.mkdir(exist_ok=True)
    make_fixture(music / "Imported repeated chords.mid")
    runtime = output / f"runtime-{time.time_ns()}"
    runtime.mkdir()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    for name, folder in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"),
                         ("XDG_CACHE_HOME", "cache")):
        environment[name] = str(runtime / folder)
    adapter = TestMidiInput()
    engine = PracticeEngine(runtime / "backend-data", enable_midi=True)
    engine.library.update(fullscreen=False)
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    Handler.engine = engine
    desktop = None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    transcript = output / "godot.log"
    journal = []

    def log(message, **details):
        entry = {"event": message, "at": time.monotonic(), **details}
        journal.append(entry)
        (output / "learner.json").write_text(json.dumps(journal, indent=2))
        print("TEACHING_LEARNER:", message, details, flush=True)

    def until(predicate, label, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            content = transcript.read_text(errors="replace") if transcript.exists() else ""
            if desktop is not None and desktop.poll() is not None:
                raise RuntimeError(f"Godot exited during {label}:\n{content}")
            if any(token in content for token in ("SCRIPT ERROR", "ERROR:", "TEACHING_FAIL:")):
                raise RuntimeError(f"Godot failed during {label}:\n{content}")
            value = predicate(content)
            if value:
                return value
            time.sleep(.025)
        raise RuntimeError(f"Timed out: {label}\n{content}")

    try:
        with patch("mido.get_input_names", return_value=[PIANO]), patch("mido.open_input", adapter.open):
            thread.start()
            with transcript.open("w") as ui_log:
                desktop = subprocess.Popen([godot, "--path", str(ROOT / "godot"),
                    "--resolution", f"{resolution[0]}x{resolution[1]}", "--audio-driver", "Dummy", "--script",
                    str(ROOT / "tests/godot/teaching_journey.gd"), "--", str(output), str(music),
                    str(resolution[0]), str(resolution[1])],
                    cwd=ROOT, env=environment, stdout=ui_log, stderr=subprocess.STDOUT)
                until(lambda text: "TEACHING_STAGE:wrong-ready" in text, "normal UI import and both-hand Learn")
                state = engine.state()
                (output / "guided-initial.json").write_text(json.dumps(state, indent=2))
                assert engine.source == str((music / "Imported repeated chords.mid").resolve())
                assert state["mode"] == "learn" and state["phase"] == "guided_wait"
                assert state["hand"] == "both" and state["teaching"]["target_count"] == 4
                assert state["last_bar"] - state["first_bar"] == 1
                assert sorted(n["pitch"] for n in state["teaching"]["expected_notes"]) == [48, 64, 67]
                assert not state["teaching"]["hint_visible"]
                assert engine.plan is not None
                identities = {f"{engine.plan.identity}:{i}": n for i, n in
                              zip(engine.plan.active_variant.source_indices, engine.plan.active_variant.notes)}
                adapter.send(61)
                wrong = engine.state()
                assert wrong["teaching"]["target_index"] == 0
                assert wrong["teaching"]["hint_reason"] == "wrong_note"
                assert wrong["teaching"]["heard_pitches"] == [61]
                log("wrong note retains target and reveals exact hint", expected=[48, 64, 67], heard=61)
                until(lambda text: "TEACHING_STAGE:hint-rendered" in text, "rendered wrong-note keyboard")
                adapter.send(61, False)
                # Deliberately slow acquisition: there is no timed miss or transport advance.
                time.sleep(.8)
                for index, want in enumerate(([48, 64, 67], [48, 64, 67], [50, 65, 69], [50, 65, 69])):
                    current = engine.state()
                    teaching = current["teaching"]
                    assert current["phase"] == "guided_wait" and teaching["target_index"] == index
                    expected = teaching["expected_notes"]
                    assert sorted(n["pitch"] for n in expected) == want
                    for note in expected:
                        source = identities[note["id"]]
                        assert source.pitch == note["pitch"] and source.start == note["source_beat"]
                    for pitch in want[:-1]:
                        adapter.send(pitch)
                        assert engine.state()["teaching"]["target_index"] == index, "A partial chord must wait"
                        time.sleep(.025)
                    adapter.send(want[-1])
                    completed_target = engine.state()
                    assert completed_target["teaching"]["target_index"] == index + 1
                    if index == 3:
                        done = completed_target
                        assert engine.pending_result is None and engine.recorder is None
                        (output / "guided-done.json").write_text(json.dumps(done, indent=2))
                    if index == 0:
                        # Repeated note_on while both keys are held cannot satisfy the next chord.
                        for pitch in want:
                            adapter.send(pitch)
                        assert engine.state()["teaching"]["target_index"] == 1
                        log("held repeated attacks do not advance")
                    time.sleep(.12)
                    for pitch in want:
                        adapter.send(pitch, False)
                    log("correct fresh chord advances", target=index + 1, pitches=want)
                    time.sleep(.3)
                assert done["phase"] == "guided_complete" and done["teaching"]["assisted_count"] == 1
                assert not done["teaching"]["mastery_eligible"]
                assert done["streak"] == done["mastered"] == 0
                log("guided completion is assisted and gives no mastery")
                until(lambda text: "TEACHING_STAGE:practice-playing" in text, "Try rhythm -> count-in -> moving practice")
                practice = engine.state()
                assert practice["mode"] == "practice" and practice["running"]
                assert not practice["preview_only"] and practice["midi_notes"] == 0
                assert practice["streak"] == practice["mastered"] == 0
                log("real practice clock runs after UI Try rhythm", beat=practice["clock_beat"])
                # The UI captures movement and stops. It receives no fake perfect practice answers.
                desktop.wait(timeout=15)
                content = transcript.read_text(errors="replace")
                if desktop.returncode or "TEACHING_RESULT:PASS" not in content or any(
                    token in content for token in ("SCRIPT ERROR", "ERROR:", "TEACHING_FAIL:")):
                    raise RuntimeError(f"Teaching UI failed ({desktop.returncode}):\n{content}")
                final = engine.state()
                assert not final["running"] and final["phase"] == "ready"
                assert final["streak"] == final["mastered"] == 0
                result = json.loads((output / "result.json").read_text())
                assert result["failures"] == [] and len(result["frames"]) >= 6
                log("stopped safely without false mastery", frames=len(result["frames"]))
                print(f"TEACHING JOURNEY PASSED: {len(result['frames'])} rendered frames; {output}", flush=True)
                return result
    finally:
        if desktop is not None and desktop.poll() is None:
            desktop.terminate()
            try:
                desktop.wait(timeout=5)
            except subprocess.TimeoutExpired:
                desktop.kill()
                desktop.wait(timeout=5)
        server.shutdown() if thread.is_alive() else None
        server.server_close()
        if thread.is_alive():
            thread.join(timeout=5)
        engine.connect("")
        engine.db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/piano-teaching-p1"))
    parser.add_argument("--resolution", default="1536x960", help="Desktop window WIDTHxHEIGHT")
    options = parser.parse_args()
    try:
        resolution = tuple(map(int, options.resolution.lower().split("x")))
        if len(resolution) != 2 or min(resolution) < 480:
            raise ValueError("Resolution must be WIDTHxHEIGHT, at least 480 pixels each")
        run(options.output_dir, resolution)
    except Exception as error:
        traceback.print_exc()
        print(f"TEACHING JOURNEY FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)

#!/usr/bin/env python3
"""Real Godot 1D/1E smoke: three scored passes -> new generated exercise PNG.

A synthetic MIDI performance is injected *inside the isolated test engine*.
No production endpoint accepts simulated notes. Requires real Godot,
music21, Verovio and CairoSVG; no display or USB keyboard required.

Run while the regular Piano Teacher application is closed:
  python scripts/smoke_adaptive_godot.py
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback

import mido

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from piano_teacher.practice import PlayedNote
from piano_teacher.server import PracticeEngine, Handler, ThreadingHTTPServer


def fixture(path: Path) -> None:
    midi = mido.MidiFile(ticks_per_beat=480)
    meta = mido.MidiTrack()
    meta.extend([
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
        mido.MetaMessage("set_tempo", tempo=500000, time=0),
        mido.MetaMessage("end_of_track", time=0),
    ])
    midi.tracks.append(meta)
    for hand, channel, chord in (
        ("Right Hand", 0, (60, 64, 67)),
        ("Left Hand", 1, (48,)),
    ):
        track = mido.MidiTrack([mido.MetaMessage("track_name", name=hand, time=0)])
        events = []
        for beat in range(8):
            for pitch in chord:
                events.append((beat*480, 1, pitch))
                events.append((beat*480+432, 0, pitch))
        tick = 0
        for at, active, pitch in sorted(events):
            track.append(mido.Message(
                "note_on" if active else "note_off", channel=channel,
                note=pitch, velocity=90 if active else 0, time=at-tick))
            tick = at
        track.append(mido.MetaMessage("end_of_track", time=0))
        midi.tracks.append(track)
    midi.save(path)


def until(predicate, *, timeout: float, label: str, godot: subprocess.Popen,
          transcript: Path):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if godot.poll() is not None:
            raise RuntimeError(f"{label}: Godot exited early\n{transcript.read_text(errors='replace')}")
        log = transcript.read_text(errors="replace")
        if any(token in log for token in ("SCRIPT ERROR", "Parse Error:", "Failed to load script", "PHASE0_SCORE_ERROR:")):
            raise RuntimeError(f"{label}: Godot script error\n{log}")
        result = predicate(log)
        if result:
            return result
        time.sleep(.05)
    raise RuntimeError(f"{label}: timed out\n{transcript.read_text(errors='replace')}")


def inject_full_performance(engine: PracticeEngine) -> tuple[int, int]:
    """Populate one clean attempt; use the production assessor unchanged."""
    with engine.lock:
        p = engine.plan
        assert p is not None and engine.recorder is not None and engine.running
        assert not engine.preview_only and engine.play_from_beat == 0
        phrase = p.active_phrase
        bpm = p.bpm
        assert bpm == 240, f"Expected target tempo in this smoke: {bpm}"
        seconds = 60.0 / bpm
        required = tuple(n for n in phrase.notes if p.hand == "both" or n.hand == p.hand)
        engine.recorder.presses[:] = [
            PlayedNote(n.pitch, (n.start-phrase.start)*seconds,
                       (min(n.end,phrase.end)-phrase.start)*seconds)
            for n in required
        ]
        return engine.transport_id, len(required)


def run() -> None:
    godot_exe = shutil.which("godot") or shutil.which("godot4")
    if not godot_exe:
        raise RuntimeError("Godot 4 is required")
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1",8765)) == 0:
            raise RuntimeError("Port 8765 is occupied; close Piano Teacher before this test")

    with tempfile.TemporaryDirectory(prefix="piano-adaptive-ui-") as directory:
        tmp = Path(directory)
        midi = tmp / "adaptive.mid"
        fixture(midi)
        env = dict(os.environ)
        env.update(HOME=str(tmp), XDG_DATA_HOME=str(tmp/"data"),
                   XDG_CONFIG_HOME=str(tmp/"config"))
        engine = PracticeEngine(tmp/"data", enable_midi=False)
        godot = None
        http = None
        thread = None
        log_path = tmp/"godot.log"
        try:
            engine.load(str(midi))
            assert engine.plan is not None
            assert engine.plan.active_variant.level == "skeleton"
            engine.plan.set_bpm(240)
            # Expose real Verovio/CairoSVG failures *before* starting Godot.
            # Otherwise a missing notehead can look like a silent GUI timeout.
            layout = engine.geometry()
            image = engine.engraved_png(0)
            assert len(layout["anchors"]) >= 2 and image.startswith(b"\x89PNG"), (
                "The initial generated skeleton failed engraving/raster validation")
            print(f"PASS preflight generated skeleton: {len(layout['notes'])} mapped notes, "
                  f"{len(image)} PNG bytes", flush=True)
            engine.midi_port = object()  # Isolated harness; no production mock MIDI.
            http = ThreadingHTTPServer(("127.0.0.1",8765),Handler)
            Handler.engine = engine
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            engine.library.update(fullscreen=False)
            with log_path.open("w") as out:
                godot = subprocess.Popen(
                    [godot_exe, "--headless", "--path", str(ROOT/"godot"),
                     "--", "--phase0-smoke"],
                    cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
                until(lambda log: "PHASE0_LESSON_READY:" in log,
                      timeout=100, label="first generated skeleton PNG",
                      godot=godot, transcript=log_path)
                first_revision = engine.score_revision
                last_attempt_id = engine.transport_id
                # One course step: 3 full, clean, target-speed attempts.
                for attempt in range(1,4):
                    if attempt == 1:
                        engine.start()
                    # Subsequent attempts are started by the teacher's
                    # automatic feedback/count-in loop, not by this script.
                    ident, required = inject_full_performance(engine)
                    assert ident > last_attempt_id and required >= 5
                    last_attempt_id = ident
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        state = engine.state()
                        if state["phase"] in ("feedback","loading"):
                            break
                        time.sleep(.04)
                    else:
                        raise RuntimeError(f"Clean attempt {attempt} did not finish")
                    if attempt < 3:
                        # Feedback interval ends with another automatic
                        # count-in; the next simulated take starts manually.
                        # Intervene only *after* the result is committed.
                        deadline = time.monotonic() + 8
                        while time.monotonic() < deadline:
                            state = engine.state()
                            if state["phase"] == "count_in" and engine.transport_id != ident:
                                break
                            time.sleep(.04)
                        else:
                            raise RuntimeError(f"Attempt {attempt} did not repeat")
                    print(f"PASS clean performance {attempt}/3: {required} notes", flush=True)
                # Third clean result must unlock next lesson level, not skip it.
                until(lambda log: engine.state()["lesson_level"] == "outline",
                      timeout=9, label="three-clean mastery transition",
                      godot=godot, transcript=log_path)
                assert engine.score_revision > first_revision
                until(lambda log: log.count("PHASE0_LESSON_READY:") >= 2,
                      timeout=100, label="new outline engraved PNG",
                      godot=godot, transcript=log_path)
                until(lambda log: engine.state()["phase"] == "count_in",
                      timeout=10, label="new lesson count-in after rendering",
                      godot=godot, transcript=log_path)
                overview = engine.lesson_overview()
                assert overview["steps"][0]["completed"]
                assert overview["current_step"] == 2
                assert engine.state()["required_notes"] > required
                assert engine.state()["count_in_beats"] == 8
                if any(token in log_path.read_text(errors="replace")
                       for token in ("SCRIPT ERROR", "Parse Error:", "Failed to load script")):
                    raise RuntimeError(log_path.read_text(errors="replace"))
                print("PASS generated skeleton -> outline, revision and image acknowledgement",flush=True)
                print("PASS lesson progress persisted and fresh moving count-in",flush=True)
                print("PHASE 1D/1E ADAPTIVE GODOT SMOKE PASSED",flush=True)
        finally:
            if godot:
                godot.terminate()
                try:
                    godot.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    godot.kill()
                    godot.wait(timeout=5)
            if http:
                http.shutdown()
                http.server_close()
            if thread:
                thread.join(timeout=5)
            engine.midi_port = None
            engine.db.close()


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"PHASE 1D/1E SMOKE FAILED: {exc}",file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(1)

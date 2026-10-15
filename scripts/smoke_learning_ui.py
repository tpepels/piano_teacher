#!/usr/bin/env python3
"""Rendered learning UI at three desktop sizes/fullscreen and real pause choices.

Godot uses normal application controls, HTTP and transport. Only USB MIDI device
discovery/opening uses the existing isolated test input adapter. No production
answer endpoint or forced backend phase is used. Artifacts retain actual PNGs.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from piano_teacher.server import Handler, PracticeEngine, ThreadingHTTPServer
from scripts.smoke_teaching_godot import PIANO, TestMidiInput, make_fixture


def run(output: Path) -> dict:
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        raise RuntimeError("Godot4 is required")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError("A graphical desktop is required for actual UI frames")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1",8765)) == 0:
            raise RuntimeError("Port8765 is occupied; close Piano Teacher first")
    output = output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    runtime = output/f"runtime-{time.time_ns()}"
    runtime.mkdir()
    music = output/"user-music"
    music.mkdir(exist_ok=True)
    make_fixture(music/"Imported hands and repeated chords.mid")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    for key,child in (("XDG_DATA_HOME","data"),("XDG_CONFIG_HOME","config"),("XDG_CACHE_HOME","cache")):
        env[key] = str(runtime/child)
    engine = PracticeEngine(runtime/"backend-data",enable_midi=True)
    engine.library.update(fullscreen=False)
    adapter = TestMidiInput()
    server = ThreadingHTTPServer(("127.0.0.1",8765),Handler)
    Handler.engine = engine
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    desktop = None
    transcript = output/"godot.log"
    journal = []
    last = None

    def observe():
        nonlocal last
        state = engine.state()
        key = tuple(state.get(k) for k in ("mode","phase","bpm","target_bpm","hand","play_from_beat","transport_id"))
        if key != last:
            last = key
            journal.append({"at":time.monotonic(),**{name:state.get(name) for name in
                ("mode","phase","bpm","target_bpm","hand","play_from_beat","transport_id","mastered","streak")}})
            (output/"journey.json").write_text(json.dumps(journal,indent=2))
        return state

    try:
        with patch("mido.get_input_names",return_value=[PIANO]),patch("mido.open_input",adapter.open):
            thread.start()
            with transcript.open("w") as log:
                desktop = subprocess.Popen([godot,"--path",str(ROOT/"godot"),"--resolution","1536x960",
                    "--audio-driver","Dummy","--script",str(ROOT/"tests/godot/learning_ui_review.gd"),
                    "--",str(output),str(music)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                deadline = time.monotonic()+90
                wrong_sent = False
                while desktop.poll() is None and time.monotonic() < deadline:
                    text = transcript.read_text(errors="replace")
                    if any(token in text for token in ("SCRIPT ERROR","ERROR:","LEARNING_UI_FAIL:")):
                        raise RuntimeError(f"Learning UI failed:\n{text}")
                    state = observe()
                    assert state.get("mastered",0) == state.get("streak",0) == 0
                    if "LEARNING_UI_STAGE:input-ready" in text and not wrong_sent:
                        assert state["mode"] == "learn" and state["phase"] == "guided_wait"
                        assert state["bpm"] == state["target_bpm"] == 80
                        adapter.send(61)
                        wrong_sent = True
                    if state["mode"] == "listen":
                        assert engine.recorder is None and state["midi_notes"] == 0
                    time.sleep(.01)
                if desktop.poll() is None:
                    raise RuntimeError("Learning UI journey exceeded90 seconds")
                text = transcript.read_text(errors="replace")
                if desktop.returncode or "LEARNING_UI_RESULT:PASS" not in text or any(
                    token in text for token in ("SCRIPT ERROR","ERROR:","LEARNING_UI_FAIL:")):
                    raise RuntimeError(f"Learning UI journey failed({desktop.returncode}):\n{text}")
                final = observe()
                assert not final["running"] and final["mastered"] == final["streak"] == 0
                result = json.loads((output/"result.json").read_text())
                assert result["failures"] == [] and wrong_sent
                print(f"LEARNING UI PASSED: {len(result['frames'])} actual frames; {output}",flush=True)
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
    parser.add_argument("--output-dir",type=Path,default=Path("/tmp/piano-teaching-p4"))
    options = parser.parse_args()
    try:
        run(options.output_dir)
    except Exception as error:
        traceback.print_exc()
        print(f"LEARNING UI FAILED: {error}",file=sys.stderr)
        raise SystemExit(1)

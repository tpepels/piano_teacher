#!/usr/bin/env python3
"""End-to-end Phase 0: real Godot practice screen, PNG, count-in and playback.

Requires Godot, music21, Verovio and CairoSVG, but no USB piano or display.
Use --file to test a real user-owned MIDI/MusicXML instead of a generated fixture.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from smoke_phase0 import make_fixture

URL = "http://127.0.0.1:8765"
CURSOR_RE = re.compile(r"PHASE0_CURSOR_BEAT:([0-9.]+) SCREEN_X:([-0-9.]+) VISIBLE:(true|false)")


def cursor_samples(log: str) -> list[tuple[float, float]]:
    """Accept actual, visible Godot beam coordinates only."""
    return [(float(beat), float(x)) for beat, x, visible in CURSOR_RE.findall(log)
            if visible == "true"]


def moving_cursor_observed(log: str) -> bool:
    """Reject false passes where the UI says PLAY but the line is static."""
    samples = cursor_samples(log)
    if len(samples) < 3:
        return False
    if any(samples[i][0] <= samples[i - 1][0] for i in range(1, len(samples))):
        return False
    return (samples[-1][0] - samples[0][0] >= 0.5 and
            max(x for _, x in samples) - min(x for _, x in samples) >= 8.0)


def api(route: str, data: dict | None = None, timeout: float = 90) -> dict:
    payload = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    with urlopen(Request(URL + route, data=payload, headers=headers),
                 timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"{route}: HTTP {response.status}")
        return json.load(response)


def await_condition(check, process, log: Path, *, timeout: float, description: str):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        transcript = log.read_text(errors="replace")
        if process.poll() is not None:
            raise RuntimeError(
                f"{description}: Godot exited early ({process.returncode})\n{transcript}")
        if check(transcript):
            return transcript
        if any(problem in transcript for problem in
               ("SCRIPT ERROR", "Parse Error:", "Failed to load script")):
            raise RuntimeError(f"{description}: GDScript failure\n{transcript}")
        time.sleep(.1)
    raise RuntimeError(
        f"{description}: timed out after {timeout:.0f}s\n{log.read_text(errors='replace')}")


def run(file: Path | None = None) -> int:
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        raise RuntimeError("Godot 4 is required for the actual practice scene smoke")
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 8765)) == 0:
            raise RuntimeError("Port 8765 is occupied; close the older backend first")
    with tempfile.TemporaryDirectory(prefix="piano-phase0-ui-") as directory:
        temp = Path(directory)
        fixture = temp / ("phase0" + file.suffix.lower() if file else "phase0.mid")
        if file is None:
            make_fixture(fixture)
        else:
            if not file.is_file():
                raise ValueError(f"MIDI/MusicXML file not found: {file}")
            fixture.write_bytes(file.read_bytes())
        env = dict(os.environ)
        env["XDG_DATA_HOME"] = str(temp / "data")
        env["XDG_CONFIG_HOME"] = str(temp / "config")
        env["HOME"] = str(temp)
        env["PYTHONPATH"] = str(ROOT)
        ui_log = temp / "godot.log"
        backend_log = temp / "backend.log"
        with backend_log.open("w+") as backend_output, ui_log.open("w+") as ui_output:
            backend = subprocess.Popen(
                [sys.executable, "-m", "piano_teacher.server", "--no-midi"],
                cwd=ROOT, env=env, stdout=backend_output, stderr=subprocess.STDOUT)
            godot_process = None
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if backend.poll() is not None:
                        raise RuntimeError(
                            "Backend exited: " + backend_log.read_text(errors="replace"))
                    try:
                        if api("/state", timeout=.25).get("loaded") is False:
                            break
                    except (OSError, URLError, TimeoutError):
                        time.sleep(.1)
                else:
                    raise RuntimeError("Backend did not become ready in 15 seconds")
                # Loading before UI startup forces the real initial HTTP poll
                # to engrave and fetch the score, rather than just draw Home.
                loaded = api("/load", {"path": str(fixture)})
                if not loaded.get("loaded"):
                    raise RuntimeError("Backend did not load the MIDI fixture")
                # Headless runs should not request a physical fullscreen window.
                api("/settings", {"fullscreen": False})
                api("/control", {"action": "tempo", "bpm": 240})
                godot_process = subprocess.Popen(
                    [godot, "--headless", "--path", str(ROOT / "godot"),
                     "--", "--phase0-smoke"],
                    cwd=ROOT, env=env, stdout=ui_output,
                    stderr=subprocess.STDOUT)
                await_condition(
                    lambda log: "PHASE0_SCORE_READY:" in log,
                    godot_process, ui_log, timeout=100,
                    description="Godot PNG notation display")
                print("PASS Godot scene displayed an engraved PNG score", flush=True)
                started = api("/control", {"action": "start"})
                if started.get("phase") != "count_in" or not started.get("preview_only"):
                    raise RuntimeError(f"Preview did not enter count-in: {started}")
                await_condition(
                    lambda log: "PHASE0_PHASE:count_in" in log,
                    godot_process, ui_log, timeout=10,
                    description="Godot count-in state")
                await_condition(
                    lambda log: "PHASE0_PHASE:playing" in log,
                    godot_process, ui_log, timeout=10,
                    description="Godot timed playing state")
                print("PASS Godot observed count-in and playing phases", flush=True)
                await_condition(lambda log: log.count("PHASE0_CLICK:count_in") >= 2,
                                godot_process, ui_log, timeout=6,
                                description="count-in click scheduling")
                print("PASS Godot scheduled metronome clicks for the count-in", flush=True)
                await_condition(moving_cursor_observed, godot_process, ui_log,
                                timeout=10, description="visible moving timing line")
                print("PASS Godot timing beam moves in musical time", flush=True)
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    state = api("/state", timeout=2)
                    if not state["running"]:
                        if state["mastered"] != 0 or state["phase"] != "ready":
                            raise RuntimeError("Preview changed mastery or did not finish")
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError("Timing preview did not finish at the selected BPM")
                transcript = ui_log.read_text(errors="replace")
                if any(error in transcript for error in
                       ("SCRIPT ERROR", "Parse Error:", "Failed to load script", "ERROR:")):
                    raise RuntimeError("Godot runtime error during practice:\n" + transcript)
                print("PASS silent preview finished without awarding mastery", flush=True)
                print("PHASE 0 GODOT PRACTICE SMOKE PASSED", flush=True)
                return 0
            finally:
                if godot_process is not None:
                    godot_process.terminate()
                    try:
                        godot_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        godot_process.kill()
                        godot_process.wait(timeout=5)
                backend.terminate()
                try:
                    backend.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    backend.kill()
                    backend.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path,
                        help="Use your own MIDI or MusicXML instead of the fixture")
    args = parser.parse_args()
    try:
        raise SystemExit(run(args.file))
    except Exception as exc:
        print(f"PHASE 0 GODOT SMOKE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)

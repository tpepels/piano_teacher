#!/usr/bin/env python3
"""Run the actual HTTP application with native notation and reject fallback.

.venv/bin/python scripts/smoke_native_notation.py
Add --render to retain an actual desktop screenshot beside the JSON/log evidence.
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
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def api(route, data=None):
    request = Request("http://127.0.0.1:8765" + route,
                      data=json.dumps(data).encode() if data is not None else None,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=90) as response:
        return json.load(response)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=ROOT / "midi/Ala_–_Joep_Beving.midi")
    parser.add_argument("--measure", type=int, default=9)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("/tmp/piano-native-application"))
    args = parser.parse_args(argv)
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        parser.error("Godot 4 is required")
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", 8765))
        except OSError:
            parser.error("Port 8765 is occupied; close the other application first")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "XDG_DATA_HOME": str(output / "data"),
           "XDG_CONFIG_HOME": str(output / "config"), "PYTHONPATH": str(ROOT)}
    with (output / "backend.log").open("w") as backend_log:
        backend = subprocess.Popen(
            [sys.executable, "-m", "piano_teacher.server", "--no-midi"],
            cwd=ROOT, env=env, stdout=backend_log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 15
            while True:
                if backend.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Backend failed to start; see backend.log")
                try:
                    api("/state")
                    break
                except (OSError, URLError):
                    time.sleep(.1)
            api("/load", {"path": str(args.file.resolve())})
            api("/settings", {"fullscreen": False})
            api("/control", {"action": "tempo", "bpm": 120})
            api("/control", {"action": "open_at", "bar": args.measure, "mode": "practice"})
            model = api("/score/model")
            expected_start = next(m["start_beat"] for m in model["measures"]
                                  if m["number"] == args.measure)
            command = [godot, "--resolution", "1536x960", "--audio-driver", "Dummy",
                       "--path", str(ROOT / "godot"), "--script",
                       str(ROOT / "tests/godot/native_application.gd"), "--", str(output)]
            if not args.render:
                command.insert(1, "--headless")
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                    text=True, timeout=100)
            transcript = result.stdout + result.stderr
            (output / "godot.log").write_text(transcript)
            if result.returncode or any(token in transcript for token in (
                    "SCRIPT ERROR", "Parse Error", "Native notation fallback:",
                    "Native Verovio glyph fallback:")):
                raise RuntimeError(transcript)
            report = json.loads((output / "native-application.json").read_text())
            if not (report["native_ready"] and report["visible"] and
                    report["drawn_noteheads"] > 0 and report["linear_timeline"]):
                raise RuntimeError(str(report))
            if abs(report["play_from_beat"] - expected_start) > 1e-7:
                raise RuntimeError("Native playback did not start at the requested source measure")
            print("NATIVE_APPLICATION_PASS:", json.dumps(report))
            return 0
        finally:
            backend.terminate()
            try:
                backend.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend.kill()
                backend.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())

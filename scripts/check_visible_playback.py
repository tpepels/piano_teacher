#!/usr/bin/env python3
"""Exercise real HTTP practice timing in a rendered Godot desktop window.

Run from a graphical Linux session, for example:
  python scripts/check_visible_playback.py --output-dir /tmp/piano-visible

The ordinary run.sh launcher starts both processes. PNG frames, measured
note positions and its log are retained. Port 8765 must be unused.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8765"


def request(route: str, payload: dict | None = None, *, raw: bool = False):
    body = None if payload is None else json.dumps(payload).encode()
    headers = {} if body is None else {"Content-Type": "application/json"}
    try:
        with urlopen(Request(URL + route, data=body, headers=headers), timeout=90) as response:
            result = response.read()
    except HTTPError as error:
        raise RuntimeError(f"{route}: HTTP {error.code}: {error.read().decode()}") from error
    return result if raw else json.loads(result)


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def run(output: Path, bpms: list[int], resolution: tuple[int, int]) -> None:
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        raise RuntimeError("Godot 4 is required")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError("Run this check in a graphical desktop session; it captures rendered pixels")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8765)) == 0:
            raise RuntimeError("Port 8765 is occupied; close the running Piano Teacher first")
    output.mkdir(parents=True, exist_ok=True)
    from smoke_godot import make_sparse_three_four_fixture

    fixture = output / "sparse-three-four.mid"
    make_sparse_three_four_fixture(fixture)
    environment = dict(os.environ)
    for key, folder in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"),
                        ("XDG_CACHE_HOME", "cache")):
        environment[key] = str(output / folder)
    environment["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    desktop = None
    with (output / "godot.log").open("w") as ui_log:
        try:
            width, height = resolution
            desktop = subprocess.Popen(
                [str(ROOT / "run.sh"), "--windowed", "--resolution", f"{width}x{height}",
                 "--script", str(ROOT / "tests/godot/live_playback.gd"), "--",
                 str(output), ",".join(map(str, bpms)), str(width), str(height)],
                cwd=ROOT, env=environment, stdout=ui_log, stderr=subprocess.STDOUT,
                start_new_session=True)
            deadline = time.monotonic() + 20
            while True:
                if desktop.poll() is not None:
                    raise RuntimeError("Launcher exited; see godot.log")
                try:
                    request("/state")
                    break
                except (URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Backend did not become ready in 20 seconds")
                    time.sleep(.1)
            request("/device", {"name": ""})
            request("/load", {"path": str(fixture)})
            request("/settings", {"fullscreen": False})
            # Retain the actual source raster and coordinates for reviewing a
            # failed pixel check; the UI still fetches these over its own HTTP.
            (output / "source-layout.json").write_text(json.dumps(request("/score/layout"), indent=2))
            (output / "source-score.png").write_bytes(request("/score.png?page=0", raw=True))
            deadline = time.monotonic() + 60 + sum(15 + 150 / bpm for bpm in bpms)
            previous_size = 0
            while desktop.poll() is None:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Visible playback check timed out; see godot.log")
                transcript = (output / "godot.log").read_text(errors="replace")
                for line in transcript[previous_size:].splitlines():
                    if line.startswith(("VISIBLE_STAGE:", "VISIBLE_FAIL:", "VISIBLE_RESULT:")):
                        print(line, flush=True)
                previous_size = len(transcript)
                time.sleep(.2)
            transcript = (output / "godot.log").read_text(errors="replace")
            for line in transcript[previous_size:].splitlines():
                if line.startswith(("VISIBLE_STAGE:", "VISIBLE_FAIL:", "VISIBLE_RESULT:")):
                    print(line, flush=True)
            if (desktop.returncode or "VISIBLE_RESULT:PASS" not in transcript
                    or any(error in transcript for error in ("SCRIPT ERROR", "ERROR:"))):
                raise RuntimeError(f"Visible playback check failed (Godot exit {desktop.returncode}); see godot.log")
            result = json.loads((output / "samples.json").read_text())
            print(f"PASS {len(result['samples'])} rendered samples at {bpms} BPM; artifacts: {output}", flush=True)
        finally:
            stop_process(desktop)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bpms", type=int, nargs="+", default=[30, 40, 80, 120])
    parser.add_argument("--resolution", default="1536x960")
    options = parser.parse_args()
    try:
        resolution = tuple(map(int, options.resolution.lower().split("x")))
        if len(resolution) != 2 or min(resolution) < 480:
            raise ValueError("Resolution must be WIDTHxHEIGHT, at least 480 pixels each")
        if any(bpm < 12 or bpm > 300 for bpm in options.bpms):
            raise ValueError("BPM must be between 12 and 300")
        run(options.output_dir.resolve(), options.bpms, resolution)
        return 0
    except Exception as error:
        print(f"VISIBLE PLAYBACK FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

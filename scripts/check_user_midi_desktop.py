#!/usr/bin/env python3
"""Capture real user-MIDI practice screens through the normal Godot renderer.

Unlike the SVG / ScoreStrip pixel test, this checks the actual 1536x960 HUD,
stage, staff rails, count-in and moving music. Requires a graphical session:
  .venv/bin/python scripts/check_user_midi_desktop.py --out /tmp/piano-midi-desktop
For CI use xvfb-run; --headless is NOT a pixel-rendering substitute.
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
from urllib.request import Request, urlopen

from check_user_midi_visual_regression import CASES, ROOT, MIDI_DIR, _name


HOST = "http://127.0.0.1:8765"


def wait_backend(server: subprocess.Popen, logfile: Path) -> None:
    for _ in range(120):
        if server.poll() is not None:
            raise RuntimeError(f"Backend exited unexpectedly:\n{logfile.read_text()}")
        try:
            with urlopen(HOST + "/state", timeout=.25) as response:
                state = json.load(response)
            if state.get("loaded") is False:
                return
        except (OSError, TimeoutError):
            time.sleep(.1)
    raise RuntimeError("Backend did not start in 12 seconds")


def api(route: str, data: dict) -> dict:
    req = Request(HOST + route, data=json.dumps(data).encode(),
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=95) as response:
        assert response.status == 200, (route, response.status)
        return json.load(response)


def run_one(filename: str, out: Path, godot: str) -> dict:
    folder = out / _name(filename)
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["HOME"] = str(folder)
    for key, path in (("XDG_DATA_HOME", "data"),
                      ("XDG_CONFIG_HOME", "config"),
                      ("XDG_CACHE_HOME", "cache")):
        env[key] = str(folder / path)
    with (folder / "backend.log").open("w") as server_log, (folder / "godot.log").open("w") as ui_log:
        server = subprocess.Popen([sys.executable, "-m", "piano_teacher.server", "--no-midi"],
                                  cwd=ROOT, env=env, stdout=server_log, stderr=subprocess.STDOUT)
        try:
            wait_backend(server, folder / "backend.log")
            source = (MIDI_DIR / filename).resolve()
            assert api("/load", {"path": str(source)}).get("loaded")
            api("/settings", {"fullscreen": False})
            cmd = [godot, "--path", str(ROOT / "godot"),
                   "--windowed", "--resolution", "1536x960",
                   "--rendering-method", "gl_compatibility",
                   "--audio-driver", "Dummy",
                   "--script", str(ROOT / "tests/godot/user_midi_desktop_capture.gd"),
                   "--", str(folder)]
            ui = subprocess.run(cmd, cwd=ROOT, env=env, stdout=ui_log,
                                stderr=subprocess.STDOUT, timeout=150)
            transcript = (folder / "godot.log").read_text(errors="replace")
            if ui.returncode or "MIDI_DESKTOP_FAILURES:0" not in transcript or "SCRIPT ERROR" in transcript:
                raise AssertionError(f"Godot desktop capture failed for {filename}:\n{transcript[-8000:]}")
            report = json.loads((folder / "desktop-report.json").read_text())
            assert not report["errors"], report["errors"]
            assert {x["frame"] for x in report["frames"]} == {"ready", "count-in", "playing"}
            for frame in ("ready", "count-in", "playing"):
                assert (folder / (frame + ".png")).stat().st_size >= 10000
            print(f"PASS DESKTOP {filename}: {len(report['frames'])} captured frames",
                  flush=True)
            return {"filename": filename, "frames": report["frames"],
                    "folder": str(folder.relative_to(out))}
        finally:
            server.terminate()
            try:
                server.wait(timeout=4)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/tmp/piano-midi-desktop"))
    parser.add_argument("--only", help="Case-insensitive substring in filename")
    args = parser.parse_args()
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        parser.error("This captures actual desktop pixels: start a display or use xvfb-run")
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        parser.error("Godot 4 executable not found")
    cases = [name for name, _ in CASES[:3]
             if not args.only or args.only.casefold() in name.casefold()]
    if not cases:
        parser.error("No selected MIDI files")
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 8765)) == 0:
            parser.error("Port 8765 is occupied, close the existing backend")
    args.out.mkdir(parents=True, exist_ok=True)
    results, failures = [], []
    for filename in cases:
        try:
            results.append(run_one(filename, args.out, godot))
        except Exception as exc:
            failures.append({"filename": filename, "error": str(exc)})
            print(f"FAIL DESKTOP {filename}: {exc}", file=sys.stderr, flush=True)
    (args.out / "summary.json").write_text(json.dumps({
        "passed": len(results), "failed": len(failures),
        "results": results, "failures": failures}, indent=2) + "\n")
    print(f"Desktop visual regression: {len(results)} passed, "
          f"{len(failures)} failed. Evidence: {args.out}", flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Launch the actual Godot scene against a real local backend, without a display.

Unlike the GDScript parser check, this runs _ready(), creates the interface
and exercises startup HTTP requests. It cannot inspect pixels, sound or USB.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8765/state"


def run() -> int:
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        raise RuntimeError("Godot 4 is required for the UI smoke test")
    with socket.socket() as connection:
        if connection.connect_ex(("127.0.0.1", 8765)) == 0:
            raise RuntimeError("Port 8765 is already in use")
    with tempfile.TemporaryDirectory(prefix="piano-phase0-ui-") as directory:
        env = dict(os.environ)
        env["XDG_DATA_HOME"] = str(Path(directory) / "data")
        env["XDG_CONFIG_HOME"] = str(Path(directory) / "config")
        env["HOME"] = directory
        env["PYTHONPATH"] = str(ROOT)
        backend = subprocess.Popen(
            [sys.executable, "-m", "piano_teacher.server", "--no-midi"],
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if backend.poll() is not None:
                    raise RuntimeError("Backend exited before readiness: " + backend.stdout.read())
                try:
                    with urlopen(URL, timeout=.2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError("Backend not ready within 15 seconds")
            result = subprocess.run(
                [godot, "--headless", "--path", str(ROOT / "godot"),
                 "--quit-after", "120"], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=45, check=False,
            )
            log = result.stdout + "\n" + result.stderr
            problems = ("SCRIPT ERROR", "Parse Error:", "Failed to load script", "ERROR:")
            if result.returncode or any(problem in log for problem in problems):
                raise RuntimeError(f"Godot scene startup failed ({result.returncode}):\n{log}")
            print("PHASE 0 GODOT HEADLESS UI SMOKE PASSED", flush=True)
            return 0
        finally:
            backend.terminate()
            try:
                backend.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                backend.kill()
                backend.communicate(timeout=5)


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"PHASE 0 GODOT SMOKE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)

"""A cold Verovio engraving must not stall the engine's command/tick worker.

Runs the real GDExtension with embedded CPython against an isolated library.
Before the dedicated asset worker, every state read and musical tick queued
behind the seconds-long score.native_layout command.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig

import pytest

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so"
FIXTURE = "Moonlight_Sonata_I.midi"


@pytest.mark.skipif(shutil.which("godot") is None or not BINARY.exists(),
                    reason="Godot or the native bridge is unavailable")
def test_cold_engraving_runs_beside_the_tick_worker(tmp_path):
    home = tmp_path / "home"
    music = home / "Music" / "Piano Teacher"
    music.mkdir(parents=True)
    shutil.copy(ROOT / "midi" / FIXTURE, music / FIXTURE)
    site = sysconfig.get_paths()["purelib"]
    env = dict(os.environ, HOME=str(home),
               XDG_CONFIG_HOME=str(tmp_path / "config"),
               XDG_DATA_HOME=str(tmp_path / "data"),
               XDG_CACHE_HOME=str(tmp_path / "cache"),
               PIANO_TEACHER_PYTHON_HOME=sys.base_prefix,
               PYTHONPATH=f"{ROOT}:{site}")
    libdir = sysconfig.get_config_var("LIBDIR")
    if libdir:
        env["LD_LIBRARY_PATH"] = f"{libdir}:{env.get('LD_LIBRARY_PATH', '')}"
    result = subprocess.run(
        ["godot", "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/native_asset_worker.gd"), "--", FIXTURE],
        capture_output=True, text=True, timeout=150, env=env)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    match = re.search(r"layout_ms=(\d+) snapshots_during_layout=(\d+) anchors_ok=true", output)
    assert match, output
    layout_ms, snapshots = int(match[1]), int(match[2])
    assert layout_ms >= 300, f"engraving was not cold ({layout_ms} ms); test proves nothing"
    # The worker answered state reads throughout: at least one every ~100 ms.
    print(f"NATIVE_ASSET_WORKER_MEASURED layout_ms={layout_ms} snapshots={snapshots}")
    assert snapshots >= layout_ms // 100, (layout_ms, snapshots)

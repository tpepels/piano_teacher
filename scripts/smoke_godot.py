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

def make_sparse_three_four_fixture(path: Path) -> None:
    """Two 3/4 bars, one active hand and silent bass, as in the reported bug."""
    import mido
    midi = mido.MidiFile(ticks_per_beat=480)
    meta = mido.MidiTrack([
        mido.MetaMessage("set_tempo", tempo=500000, time=0),
        mido.MetaMessage("time_signature", numerator=3, denominator=4, time=0),
        mido.MetaMessage("end_of_track", time=0)
    ])
    midi.tracks.append(meta)
    hand = mido.MidiTrack([mido.MetaMessage("track_name", name="Right Hand", time=0)])
    last = 0
    for index, pitch in enumerate((77, 77, 77, 76, 76, 76)):
        at = index * 480
        hand.append(mido.Message("note_on", note=pitch, velocity=85, channel=0, time=at-last))
        hand.append(mido.Message("note_off", note=pitch, velocity=0, channel=0, time=240))
        last = at + 240
    hand.append(mido.MetaMessage("end_of_track", time=240))
    midi.tracks.append(hand)
    midi.save(path)


URL = "http://127.0.0.1:8765"
CURSOR_RE = re.compile(
    r"^PHASE0_CURSOR_BEAT:([0-9.]+) SCREEN_X:([-0-9.]+) "
    r"VISIBLE:(true|false) CONTENT_X:([-0-9.]+)", re.MULTILINE
)


LEAD_RE = re.compile(r"PHASE0_LEAD_BEAT:([-0-9.]+) CONTENT_X:([-0-9.]+) CURSOR_X:([-0-9.]+) VISIBLE:(true|false)")


def moving_lead_in_observed(log: str, *, count_in_beats: float = 3.0) -> bool:
    """Allow genuine 1/8 pickups: their entire lead spans only half a beat.

    The ordinary count-in still needs three ordered samples and 20px travel.
    A short pickup needs two samples and proportionately less travel, but
    must still advance against a stationary cursor. No silent test skip.
    """
    samples = [(float(beat), float(x), float(beam))
               for beat, x, beam, show in LEAD_RE.findall(log) if show == "true"]
    short = count_in_beats < 1.0
    minimum_samples = 2 if short else 3
    minimum_span = min(.5, count_in_beats * .35)
    minimum_pixels = 8 if short else 20
    if len(samples) < minimum_samples or samples[-1][0] - samples[0][0] < minimum_span:
        return False
    return (all(samples[i][0] > samples[i-1][0] for i in range(1, len(samples)))
            and max(x for _, x, _ in samples) - min(x for _, x, _ in samples) >= minimum_pixels
            and max(b for _, _, b in samples) - min(b for _, _, b in samples) <= 30)


def cursor_samples(log: str) -> list[tuple[float, float, float]]:
    """Keep visible playback beam and score positions from the same frame."""
    return [(float(beat), float(beam), float(content))
            for beat, beam, visible, content in CURSOR_RE.findall(log)
            if visible == "true" and float(beat) > 0.0]


def moving_cursor_observed(log: str) -> bool:
    """Require leftward playback scrolling beneath a stable timing line."""
    samples = cursor_samples(log)
    if len(samples) < 3:
        return False
    if any(samples[i][0] <= samples[i - 1][0] for i in range(1, len(samples))):
        return False
    if any(samples[i][2] > samples[i - 1][2] + 1.0 for i in range(1, len(samples))):
        return False
    beam_motion = max(beam for _, beam, _ in samples) - min(beam for _, beam, _ in samples)
    score_motion = samples[0][2] - samples[-1][2]
    return (samples[-1][0] - samples[0][0] >= 0.5
            and score_motion >= 8.0 and beam_motion <= 30.0)


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
               ("SCRIPT ERROR", "Parse Error:", "Failed to load script", "PHASE0_SCORE_ERROR:")):
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
            make_sparse_three_four_fixture(fixture)
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
                # Real MIDI files can have an eighth-note pickup (0.5 beat).
                # At forced 240 BPM that is only 125ms, shorter than one
                # normal state poll; the visual smoke would miss count-in.
                api("/control", {"action": "tempo", "bpm": 80 if file else 240})
                godot_process = subprocess.Popen(
                    [godot, "--headless", "--resolution", "1536x960", "--path", str(ROOT / "godot"),
                     "--", "--phase0-smoke"],
                    cwd=ROOT, env=env, stdout=ui_output,
                    stderr=subprocess.STDOUT)
                await_condition(
                    lambda log: "PHASE0_SCORE_READY:" in log,
                    godot_process, ui_log, timeout=100,
                    description="Godot PNG notation display")
                print("PASS Godot scene displayed an engraved PNG score", flush=True)
                geom = api("/score/layout")
                print("REAL SCORE NOTE GEOMETRY:", json.dumps(geom.get("notes", [])[:4]), flush=True)
                print("REAL SCORE CURSOR ANCHORS:", json.dumps(geom.get("anchors", [])[:4]), flush=True)
                from xml.etree import ElementTree as ET
                with urlopen(URL + "/score.svg?page=0", timeout=15) as response:
                    root = ET.fromstring(response.read())
                print("REAL SVG ROOT:", json.dumps(root.attrib), flush=True)
                parent_map = {child: parent for parent in root.iter() for child in parent}
                first_note = next((e for e in root.iter()
                                   if "note" in e.get("class", "").split()), None)
                if first_note is not None:
                    glyph = next((e for e in first_note.iter()
                                  if e.tag.rsplit("}", 1)[-1] == "use"), first_note)
                    chain = []
                    node = glyph
                    while node is not None:
                        chain.append({"tag": node.tag.rsplit("}", 1)[-1], **node.attrib})
                        node = parent_map.get(node)
                    print("REAL SVG NOTE TRANSFORMS:", json.dumps(chain[:12]), flush=True)
                started = api("/control", {"action": "start"})
                if started.get("phase") != "count_in" or not started.get("preview_only"):
                    raise RuntimeError(f"Preview did not enter count-in: {started}")
                await_condition(
                    lambda log: "PHASE0_PHASE:count_in" in log,
                    godot_process, ui_log, timeout=10,
                    description="Godot count-in state")
                lead_seconds = started["count_in_beats"] * 60.0 / started["bpm"]
                await_condition(
                    lambda log: "PHASE0_PHASE:playing" in log,
                    godot_process, ui_log, timeout=max(10, lead_seconds + 8),
                    description="Godot timed playing state")
                print("PASS Godot observed count-in and playing phases", flush=True)
                # Moving cursor logs can pass with every printed note offscreen.
                # Demand that Godot's actual cropped-PNG-to-panel transform
                # leaves an engraved required notehead inside the viewport.
                await_condition(
                    lambda log: re.search(r"PHASE0_VISIBLE_NOTES:([1-9][0-9]*)", log) is not None,
                    godot_process, ui_log, timeout=5,
                    description="engraved noteheads actually visible while playing")
                print("PASS played notes remain visible in the Godot panel", flush=True)
                await_condition(
                    lambda log: moving_lead_in_observed(
                        log, count_in_beats=float(started["count_in_beats"])),
                    godot_process, ui_log,
                    timeout=6, description="count-in musical movement")
                print("PASS count-in score moves under a stable timing line", flush=True)
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

#!/usr/bin/env python3
"""Real Phase 0 MIDI -> Verovio -> PNG -> in-memory commands -> count-in."""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mido
from piano_teacher.server import PracticeEngine
from piano_teacher.inprocess import EngineCommands

def make_fixture(path: Path) -> None:
    midi = mido.MidiFile(ticks_per_beat=480)
    meta = mido.MidiTrack()
    meta.extend([
        mido.MetaMessage("set_tempo", tempo=500000, time=0),
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
        mido.MetaMessage("end_of_track", time=0),
    ])
    midi.tracks.append(meta)
    for channel, label, pitches in (
        (0, "Right Hand", (64, 67, 69, 72, 69, 67, 65, 64)),
        (1, "Left Hand", (48, 52, 53, 55, 53, 52, 50, 48)),
    ):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=label, time=0))
        for pitch in pitches:
            track.append(mido.Message("note_on", channel=channel, note=pitch,
                                      velocity=90, time=0))
            track.append(mido.Message("note_off", channel=channel, note=pitch,
                                      velocity=0, time=480))
        track.append(mido.MetaMessage("end_of_track", time=0))
        midi.tracks.append(track)
    midi.save(path)


def query(commands: EngineCommands, path: str, data: dict | None = None):
    method = "POST" if data is not None else "GET"
    status, response = commands.request(
        method, path, json.dumps(data) if data is not None else "")
    if status != 200:
        if path == "/library/open" and data == {"id": "../outside.mid"}:
            assert status == 400 and "error" in json.loads(response)
            return "application/json", response
        raise RuntimeError(f"{path}: command {status}: {response.decode()}")
    return ("image/png" if path.startswith("/score.png") else "application/json"), response


def check(path: Path | None = None):
    from PIL import Image
    with tempfile.TemporaryDirectory(prefix="piano-phase0-") as directory:
        temp = Path(directory)
        library = temp / "music"
        library.mkdir()
        target = library / ("smoke" + path.suffix.lower() if path else "smoke.mid")
        if path:
            target.write_bytes(path.read_bytes())
        else:
            make_fixture(target)
        engine = PracticeEngine(temp / "data", enable_midi=False)
        commands = EngineCommands(engine=engine)
        try:
            query(commands, "/settings", {"music_dir": str(library)})
            _, data = query(commands, "/library")
            items = json.loads(data)["pieces"]
            assert len(items) == 1, "Generated/imported score missing from library"
            _, data = query(commands, "/library/open", {"id": items[0]["id"]})
            state = json.loads(data)
            assert state["loaded"] and state["exercise_count"] >= 1
            print(f"PASS import: {state['title']}, {state['exercise_count']} exercise(s)", flush=True)
            _, data = query(commands, "/score/layout")
            layout = json.loads(data)
            assert layout["pages"] > 0 and layout["anchors"], "Engraving has no note coordinates"
            print(f"PASS engraving: {layout['pages']} page(s), {len(layout['anchors'])} anchors", flush=True)
            mime, image = query(commands, "/score.png?page=0")
            assert mime == "image/png" and image.startswith(b"\\x89PNG\\r\\n\\x1a\\n".decode("unicode_escape").encode("latin1"))
            with Image.open(BytesIO(image)) as png:
                png.verify()
                assert png.width >= 600 and png.height >= 30
            print("PASS rendered score: valid PNG pixels", flush=True)
            _, data = query(commands, "/control", {"action": "start"})
            beginning = json.loads(data)
            assert beginning["phase"] == "count_in" and beginning["preview_only"]
            _, paused_raw = query(commands, "/control", {"action": "pause"})
            paused = json.loads(paused_raw)
            assert paused["phase"] == "paused" and paused["clock_beat"] < 0
            _, resumed_raw = query(commands, "/control", {"action": "resume"})
            resumed = json.loads(resumed_raw)
            assert resumed["phase"] == "count_in"
            assert resumed["transport_id"] == beginning["transport_id"]
            _, restarted_raw = query(commands, "/control", {"action": "restart"})
            restarted = json.loads(restarted_raw)
            assert restarted["phase"] == "count_in"
            assert restarted["transport_id"] > beginning["transport_id"]
            engine.run_at = time.monotonic() - .25
            assert json.loads(query(commands, "/state")[1])["phase"] == "playing"
            engine.run_at = time.monotonic() - beginning["duration"] - 1
            ending = json.loads(query(commands, "/state")[1])
            assert not ending["running"] and ending["mastered"] == 0
            query(commands, "/library/open", {"id": "../outside.mid"})
            print("PASS in-process practice clock, preview and command handling", flush=True)
        finally:
            engine.db.close()
    print("PHASE 0 EMBEDDED ENGINE SMOKE PASSED", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path)
    options = parser.parse_args()
    try:
        check(options.file)
        return 0
    except Exception as exc:
        print(f"PHASE 0 SMOKE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

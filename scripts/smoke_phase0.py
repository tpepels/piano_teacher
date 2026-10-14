#!/usr/bin/env python3
"""Real Phase 0 smoke: MIDI/MusicXML -> Verovio -> PNG -> HTTP -> count-in.

Run: python scripts/smoke_phase0.py [--file /path/to/score.mid]
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mido
from piano_teacher.server import Handler, PracticeEngine, ThreadingHTTPServer


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


def query(url: str, path: str, data: dict | None = None):
    content = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"} if content else {}
    try:
        with urlopen(Request(url + path, data=content, headers=headers), timeout=90) as r:
            return r.headers.get_content_type(), r.read()
    except HTTPError as exc:
        if path == "/library/open" and data == {"id": "../outside.mid"}:
            if exc.code != 400 or "error" not in json.loads(exc.read()):
                raise AssertionError("Unsafe library request did not give a JSON error")
            return "application/json", b'{"error":"expected rejection"}'
        raise RuntimeError(f"{path}: HTTP {exc.code}: {exc.read().decode()}") from exc


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
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        Handler.engine = engine
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f"http://127.0.0.1:{server.server_port}"
        try:
            query(root, "/settings", {"music_dir": str(library)})
            _, data = query(root, "/library")
            items = json.loads(data)["pieces"]
            assert len(items) == 1, "Generated/imported score missing from library"
            _, data = query(root, "/library/open", {"id": items[0]["id"]})
            state = json.loads(data)
            assert state["loaded"] and state["exercise_count"] >= 1
            print(f"PASS import: {state['title']}, {state['exercise_count']} exercise(s)", flush=True)
            _, data = query(root, "/score/layout")
            layout = json.loads(data)
            assert layout["pages"] > 0 and layout["anchors"], "Engraving has no note coordinates"
            print(f"PASS engraving: {layout['pages']} page(s), {len(layout['anchors'])} anchors", flush=True)
            mime, image = query(root, "/score.png?page=0")
            assert mime == "image/png" and image.startswith(b"\\x89PNG\\r\\n\\x1a\\n".decode("unicode_escape").encode("latin1"))
            with Image.open(BytesIO(image)) as png:
                png.verify()
                assert png.width >= 600 and png.height >= 30
            print("PASS rendered score: valid PNG pixels", flush=True)
            _, data = query(root, "/control", {"action": "start"})
            beginning = json.loads(data)
            assert beginning["phase"] == "count_in" and beginning["preview_only"]
            engine.run_at = time.monotonic() - .25
            assert json.loads(query(root, "/state")[1])["phase"] == "playing"
            engine.run_at = time.monotonic() - beginning["duration"] - 1
            ending = json.loads(query(root, "/state")[1])
            assert not ending["running"] and ending["mastered"] == 0
            query(root, "/library/open", {"id": "../outside.mid"})
            print("PASS HTTP practice clock, device-free preview and error handling", flush=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            engine.db.close()
    print("PHASE 0 BACKEND SMOKE PASSED", flush=True)


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

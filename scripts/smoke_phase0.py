#!/usr/bin/env python3
"""Real Phase 0 MIDI -> native engraving -> typed commands -> count-in."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

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


def query(commands: EngineCommands, operation: str, data: dict | None = None) -> dict:
    """Execute the actual typed in-process operation (no route emulation)."""
    status, response = commands.request(
        operation, json.dumps(data) if data is not None else "{}")
    decoded = json.loads(response)
    if status != 0:
        raise RuntimeError(f"{operation}: status {status}: {decoded}")
    if not isinstance(decoded, dict):
        raise TypeError(f"{operation} did not return a JSON object")
    return decoded


def check(path: Path | None = None) -> None:
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
            settings = query(commands, "settings.update", {"music_dir": str(library)})
            assert settings["music_dir"] == str(library)
            listing = query(commands, "library.catalog")
            pieces = listing["pieces"]
            assert len(pieces) == 1, "MIDI fixture missing from actual library"
            state = query(commands, "library.open", {"id": pieces[0]["id"]})
            revision = int(state["revision"])
            assert state["loaded"] and state["exercise_count"] >= 1
            print(f"PASS import: {state['title']}, {state['exercise_count']} exercises", flush=True)

            layout = query(commands, "score.native_layout")
            assert int(layout.get("revision", -1)) == revision and layout.get("anchors"), (
                "Native engraving must supply the source note anchors")
            print(f"PASS native engraving: {len(layout['anchors'])} anchors", flush=True)

            model = query(commands, "score.semantic")
            assert int(model.get("revision", -1)) == revision and model.get("notes"), (
                "Engraving and model must describe the same selected revision")
            print(f"PASS semantic score: {len(model['notes'])} notes", flush=True)

            acknowledged = query(commands, "practice.command",
                                 {"action": "score_ready", "revision": revision})
            assert acknowledged["loaded"] and acknowledged["phase"] != "loading", (
                "Native score must acknowledge its selected revision")

            started = query(commands, "practice.command", {"action": "start"})
            assert started["phase"] == "count_in" and started["preview_only"], (
                "Software-only playback must count in without awarding mastery")
            first_transport = started["transport_id"]
            paused = query(commands, "practice.command", {"action": "pause"})
            assert paused["paused"] and paused["clock_beat"] < 0
            resumed = query(commands, "practice.command", {"action": "resume"})
            assert resumed["running"] and not resumed["paused"]
            assert resumed["transport_id"] == first_transport
            restarted = query(commands, "practice.command", {"action": "restart"})
            assert restarted["running"] and restarted["transport_id"] > first_transport
            assert restarted["mastered"] == 0
            denied, error = commands.request("library.open", '{"id":"../outside.mid"}')
            assert denied == 1 and "error" in json.loads(error)
            print("PASS typed MIDI transport and library containment", flush=True)
        finally:
            engine.db.close()
    print("PHASE 0 TYPED IN-PROCESS SMOKE PASSED", flush=True)


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

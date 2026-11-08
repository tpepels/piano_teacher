"""A stopped score's long-rest preview keeps lesson names on native attacks."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import mido
import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.mark.skipif(GODOT is None, reason="Godot 4 unavailable")
def test_ready_step_marker_follows_actual_native_head_after_long_opening_rest(tmp_path):
    from piano_teacher.server import PracticeEngine

    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    for name, beat, pitch in (("Right Hand", 8, 72), ("Left Hand", 12, 48)):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=name))
        track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
        track.append(mido.Message("note_on", note=pitch, velocity=80, time=beat*480))
        track.append(mido.Message("note_off", note=pitch, time=480))
        track.append(mido.MetaMessage("end_of_track", time=(15-beat)*480))
        midi.tracks.append(track)
    source = tmp_path / "opening-rest.mid"
    midi.save(source)
    engine = PracticeEngine(tmp_path / "engine", enable_midi=False)
    try:
        engine.load(str(source))
        engine._prepare_perform(scope="whole")
        payload = {"model": engine.semantic_score(), "layout": engine.geometry()}
        assert {n["onset_beats"] for n in payload["model"]["notes"]} == {8, 12}
    finally:
        engine.listen.cancel()
        engine.db.close()
    fixture = tmp_path / "native.json"
    fixture.write_text(json.dumps(payload))
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--audio-driver", "Dummy", "--script",
         str(ROOT / "tests/godot/ready_step_marker.gd"), "--", str(fixture)],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "XDG_DATA_HOME": str(tmp_path / "data"),
             "XDG_CONFIG_HOME": str(tmp_path / "config")})
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert not any(token in output for token in ("SCRIPT ERROR", "Parse Error", "ERROR:")), output
    assert "READY_STEP_MARKER_FAILURES:0" in output, output

"""Python/Godot Listen and visual transport use the same tempo mapping.

The numerical oracle is the Python TempoMap used by grading and WAV
rendering; the optional Godot script tests the actual client implementation.
"""
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher.exercise_contracts import TempoMap, TempoSegment

ROOT = Path(__file__).resolve().parents[1]


def test_shaped_beat_and_audio_seconds_share_server_reference():
    tempo = TempoMap("research", (
        TempoSegment(0, 2, 30),
        TempoSegment(2, 4, 60),
        TempoSegment(4, 6, 120),
    ))
    expected = [(0, 0), (1, 2), (2, 4), (3, 5),
                (4, 6), (5, 6.5), (6, 7)]
    assert [(beat, tempo.seconds_at(beat)) for beat, _ in expected] == expected
    assert all(tempo.beat_at(seconds) == pytest.approx(beat)
               for beat, seconds in expected)
    assert [segment["start_seconds"] for segment in tempo.as_segments()] == [
        0, 4, 6]


def test_listen_and_visual_client_consume_shared_tempo_timeline():
    # Guard against the formerly constant-BPM audio drift correction.
    demo = (ROOT / "godot/demo_player.gd").read_text()
    main = (ROOT / "godot/main.gd").read_text()
    clock = (ROOT / "godot/visual_transport_clock.gd").read_text()
    assert "TempoTimeline.seconds_at_beat(visual_beat, bpm, segments)" in demo
    assert 'state.get("tempo_segments", [])' in demo
    assert 'last_state.get("tempo_segments", [])' in main
    assert "TempoTimeline.beat_at_seconds(seconds, bpm, segments)" in clock
    assert "visual_beat * 60.0 / bpm" not in demo


@pytest.mark.skipif(shutil.which("godot") is None and shutil.which("godot4") is None,
                    reason="Godot 4 unavailable on short Python CI")
def test_godot_tempo_conversion_matches_python_reference():
    godot = shutil.which("godot") or shutil.which("godot4")
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/tempo_timeline.gd")],
        capture_output=True, text=True, timeout=20)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "TEMPO_TIMELINE_FAILURES:0" in output

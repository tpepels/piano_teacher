"""Actual generated PCM and deterministic practice tick policy, without Main."""
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess

import pytest


@pytest.fixture(scope="module")
def capture(tmp_path_factory):
    binary = shutil.which("godot") or shutil.which("godot4")
    if binary is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    folder = tmp_path_factory.mktemp("practice-metronome")
    result = subprocess.run(
        [binary, "--headless", "--audio-driver", "Dummy", "--path", str(root / "godot"),
         "--script", str(root / "tests/godot/practice_metronome.gd"), "--", str(folder)],
        capture_output=True, text=True, timeout=30,
    )
    return folder, result


def require_capture(capture):
    folder, result = capture
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output and "ERROR:" not in output, output
    assert "PRACTICE_METRONOME_FAILURES:0" in output, output
    return folder


def original_pcm(frequency):
    # Independent numerical oracle for Main's existing sound, including
    # signed-16 truncation and byte order. Do not read production constants.
    frames, rate = 4200, 44100
    values = []
    for i in range(frames):
        t = i / rate
        envelope = math.pow(1.0 - i / frames, 4.0)
        wave = math.sin(math.tau * frequency * t) * envelope * 0.46
        values.append(int(wave * 32767.0))
    return struct.pack("<" + "h" * frames, *values)


def assert_click(data, metadata, frequency):
    assert metadata == dict(format=1, mix_rate=44100, stereo=False,
                            volume_db=-5.0, bytes=8400)
    assert data == original_pcm(frequency)


def test_transport_count_in_pause_recovery_and_listen_policy(capture):
    require_capture(capture)


@pytest.mark.parametrize("name,frequency", [("high", 1160.0), ("low", 770.0)])
def test_generated_audio_preserves_original_pcm_and_loudness(capture, name, frequency):
    folder = require_capture(capture)
    metadata = json.loads((folder / "audio.json").read_text())
    assert_click((folder / (name + ".pcm")).read_bytes(), metadata[name], frequency)
    assert (folder / "high.pcm").read_bytes() != (folder / "low.pcm").read_bytes()


@pytest.mark.parametrize("damage", ["swapped-accent", "truncated", "quiet", "endian", "rate", "envelope"])
def test_pcm_oracle_rejects_changed_sound(capture, damage):
    folder = require_capture(capture)
    metadata = json.loads((folder / "audio.json").read_text())["high"]
    data = (folder / "high.pcm").read_bytes()
    if damage == "swapped-accent":
        data = (folder / "low.pcm").read_bytes()
    elif damage == "truncated":
        data = data[:4000]
    elif damage == "quiet":
        values = struct.unpack("<" + "h" * 4200, data)
        data = struct.pack("<" + "h" * 4200, *(int(v * .5) for v in values))
    elif damage == "endian":
        data = b"".join(data[i:i+2][::-1] for i in range(0, len(data), 2))
    elif damage == "rate":
        metadata["mix_rate"] = 48000
    else:
        data = struct.pack("<" + "h" * 4200, *(int(math.sin(math.tau * 1160 * i / 44100) * .46 * 32767) for i in range(4200)))
    with pytest.raises(AssertionError):
        assert_click(data, metadata, 1160.0)

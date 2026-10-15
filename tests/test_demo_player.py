"""Godot must play real decoded PCM and obey the backend Listen lifecycle."""
from pathlib import Path
import math
import shutil
import struct
import subprocess
import wave
import pytest

ROOT = Path(__file__).resolve().parents[1]

def test_actual_godot_audio_stream_waits_pauses_and_stops(tmp_path):
    godot = shutil.which('godot') or shutil.which('godot4')
    if not godot:
        pytest.skip('Godot unavailable')
    path = tmp_path/'note.wav'
    with wave.open(str(path), 'wb') as out:
        out.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
        out.writeframes(b''.join(struct.pack('<h', int(10000*math.sin(i*440*math.tau/44100))) for i in range(44100)))
    result = subprocess.run([godot, '--headless', '--path', str(ROOT/'godot'), '--script',
        str(ROOT/'tests/godot/demo_player.gd'), '--', str(path)], capture_output=True, text=True, timeout=20)
    output = result.stdout+result.stderr
    assert result.returncode == 0 and 'SCRIPT ERROR' not in output, output
    assert 'DEMO_PLAYER_FAILURES:0' in output

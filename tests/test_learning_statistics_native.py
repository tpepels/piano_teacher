import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig

import pytest
import mido
from learning_statistics_fixture import populate

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("godot") is None, reason="Godot unavailable")
def test_native_statistics_worker_and_real_settings_report(tmp_path):
    data = tmp_path / "data/piano-teacher"
    data.mkdir(parents=True)
    config = tmp_path / "config/piano-teacher"
    config.mkdir(parents=True)
    music = tmp_path / "music"
    music.mkdir()
    source = music / "statistics.mid"
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Right hand"))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
    for pitch in (60, 62, 64, 65):
        track.append(mido.Message("note_on", note=pitch, velocity=80, time=0 if pitch == 60 else 360))
        track.append(mido.Message("note_off", note=pitch, time=120))
    track.append(mido.MetaMessage("end_of_track", time=360))
    midi.save(source)
    populate(data / "progress.db", count=1200, fingerprint=hashlib.sha256(source.read_bytes()).hexdigest())
    (config / "settings.json").write_text(json.dumps({"music_dir": str(music), "last_piece": source.name, "fullscreen": False}))
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CONFIG_HOME": str(tmp_path / "config"),
           "XDG_CACHE_HOME": str(tmp_path / "cache"), "PIANO_TEACHER_PYTHON_HOME": sys.base_prefix,
           "PYTHONPATH": f"{ROOT}:{sysconfig.get_paths()['purelib']}", "GODOT_SILENCE_ROOT_WARNING": "1"}
    env["LD_LIBRARY_PATH"] = f"{sysconfig.get_config_var('LIBDIR')}:{env.get('LD_LIBRARY_PATH', '')}"
    result = subprocess.run(["godot", "--headless", "--path", str(ROOT / "godot"), "--script",
        str(ROOT / "tests/godot/learning_statistics_native.gd")], capture_output=True, text=True, env=env, timeout=70)
    output = result.stdout+result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    measured = re.search(r"LEARNING_STATISTICS_NATIVE_OK elapsed_ms=(\d+) snapshots=(\d+)", output)
    assert measured, output
    print(measured.group(0))

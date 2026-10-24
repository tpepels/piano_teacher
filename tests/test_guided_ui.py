"""Real Godot guided controls, hint placement and untimed score projection."""
from pathlib import Path
import shutil
import subprocess
import pytest

from test_recovery_motion import make_midi_fixture

ROOT=Path(__file__).resolve().parents[1]


def test_guided_learning_uses_real_controls_and_static_target_score(tmp_path):
    godot=shutil.which('godot') or shutil.which('godot4')
    if not godot:
        pytest.skip('Godot unavailable')
    make_midi_fixture(tmp_path, "chords", "right")
    result=subprocess.run([godot,'--headless','--path',str(ROOT/'godot'),'--script',
        str(ROOT/'tests/godot/guided_interactions.gd'), '--', str(tmp_path)],capture_output=True,text=True,timeout=20)
    output=result.stdout+result.stderr
    assert result.returncode==0,output
    assert 'SCRIPT ERROR' not in output,output
    assert 'GUIDED_UI_FAILURES:0' in output,output

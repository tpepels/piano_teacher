import os
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]

def test_native_supports_source_128ths_many_dots_and_octave_clefs():
    godot=shutil.which('godot') or shutil.which('godot4')
    if not godot:
        pytest.skip('Godot unavailable')
    p=subprocess.run([godot,'--headless','--path',str(ROOT/'godot'),'--script',
        str(ROOT/'tests/godot/advanced_values.gd')],capture_output=True,text=True,
        env={**os.environ,'PIANO_TEACHER_NATIVE_NOTATION':'1'},timeout=30)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'ADVANCED_VALUES_PASS' in p.stdout

"""Actual count-in glyphs must follow the active lesson's clef choices."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from piano_teacher.notation_symbols import preparation_symbols

ROOT=Path(__file__).resolve().parents[1]

def test_real_count_in_pixels_follow_reversed_hand_clefs(tmp_path):
    godot=shutil.which('godot') or shutil.which('godot4')
    if not godot or not os.environ.get('DISPLAY'):
        pytest.skip('Graphical Godot required')
    symbols=tmp_path/'symbols.json'
    symbols.write_text(json.dumps(preparation_symbols()))
    result=subprocess.run([godot,'--path',str(ROOT/'godot'),'--audio-driver','Dummy',
        '--script',str(ROOT/'tests/godot/fidelity_preparation.gd'),'--',str(symbols),str(tmp_path/'clef-comparison.png')],
        capture_output=True,text=True,timeout=20)
    output=result.stdout+result.stderr
    assert result.returncode==0 and 'SCRIPT ERROR' not in output,output
    assert 'FIDELITY_CLEF_FAILURES:0' in output

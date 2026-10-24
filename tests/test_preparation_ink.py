"""Verify actual count-in masking against real rendered accidental/ledger pixels."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher.music import Note, Phrase

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which('godot') or shutil.which('godot4')


@pytest.mark.skipif(not GODOT or not os.environ.get('DISPLAY'),
                    reason='Pixel regression requires Godot on an X11 desktop')
def test_count_in_preserves_actual_opening_and_recovery_accidentals_and_ledgers(tmp_path):
    notes = tuple(Note(beat, beat + .5, pitch, 0, 0, 'right')
                  for beat in range(8) for pitch in ([66, 85] if beat in (0, 4) else [65, 84]))
    from test_recovery_motion import make_phrase_fixture
    make_phrase_fixture(tmp_path, Phrase(1, 1, 2, 0, 8, notes),
                        boundaries=(0,4,8), hand="right")
    result = subprocess.run([GODOT, '--display-driver', 'x11', '--audio-driver', 'Dummy',
        '--path', str(ROOT / 'godot'), '--script', str(ROOT / 'tests/godot/preparation_ink.gd'),
        '--', str(tmp_path)], capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert 'SCRIPT ERROR' not in output, output
    assert 'PREPARATION_INK_FAILURES:0' in output, output

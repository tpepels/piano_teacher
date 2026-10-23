"""The real reading surface keeps cues clear and feedback stable across polls."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from test_score_motion_render import make_render_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_rendered_reading_cues_and_feedback_at_desktop_and_compact_sizes(tmp_path):
    godot = shutil.which('godot') or shutil.which('godot4')
    if not godot or not os.environ.get('DISPLAY'):
        pytest.skip('Actual graphical Godot required')
    make_render_fixture(tmp_path)
    result = subprocess.run([godot, '--path', str(ROOT/'godot'), '--audio-driver', 'Dummy',
        '--script', str(ROOT/'tests/godot/reading_feedback.gd'), '--', str(tmp_path)],
        capture_output=True, text=True, timeout=35)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and 'SCRIPT ERROR' not in output, output
    assert 'READING_FEEDBACK_FAILURES:0' in output

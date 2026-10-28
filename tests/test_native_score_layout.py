"""Score geometry has its own lifecycle and works without a scene/view."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_score_layout_owns_geometry_without_a_canvas():
    binary = shutil.which('godot') or shutil.which('godot4')
    if binary is None:
        pytest.skip('Godot 4 unavailable')
    root = Path(__file__).resolve().parents[1]
    assert (root/'godot/notation/native/score_layout.gd').exists(), 'Independent score layout is missing'
    run = subprocess.run([binary, '--headless', '--path', str(root/'godot'),
        '--script', str(root/'tests/godot/native_score_layout.gd')],
        capture_output=True, text=True, timeout=30)
    output = run.stdout+run.stderr
    assert run.returncode == 0 and 'SCRIPT ERROR' not in output, output
    assert 'SCORE_LAYOUT_FAILURES:0' in output, output

"""Authentic contour spacing is callable without a native view."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_authentic_ink_geometry_can_fit_source_boundaries_without_a_canvas():
    binary = shutil.which('godot') or shutil.which('godot4')
    if binary is None:
        pytest.skip('Godot 4 unavailable')
    root = Path(__file__).resolve().parents[1]
    assert (root/'godot/notation/native/ink_geometry.gd').exists(), 'Independent ink geometry is missing'
    run = subprocess.run([binary,'--headless','--path',str(root/'godot'),
        '--script',str(root/'tests/godot/native_ink_geometry.gd')],
        capture_output=True,text=True,timeout=30)
    output = run.stdout+run.stderr
    assert run.returncode == 0 and 'SCRIPT ERROR' not in output, output
    assert 'INK_GEOMETRY_FAILURES:0' in output, output

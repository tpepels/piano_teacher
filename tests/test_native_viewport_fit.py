"""Source fitting is a geometry decision, independently of view loading."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_native_viewport_fit_preserves_one_density_and_source_geometry():
    binary = shutil.which('godot') or shutil.which('godot4')
    if binary is None:
        pytest.skip('Godot 4 unavailable')
    root = Path(__file__).resolve().parents[1]
    assert (root/'godot/notation/native/viewport_fit.gd').exists(), 'Independent viewport fitter is missing'
    run = subprocess.run([binary,'--headless','--path',str(root/'godot'),
        '--script',str(root/'tests/godot/native_viewport_fit.gd')],capture_output=True,text=True,timeout=30)
    output = run.stdout+run.stderr
    assert run.returncode==0 and 'SCRIPT ERROR' not in output, output
    assert 'VIEWPORT_FIT_FAILURES:0' in output, output

"""Source connector endpoints do not require a renderer or canvas."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_connector_geometry_has_independent_source_endpoint_policy():
    binary = shutil.which('godot') or shutil.which('godot4')
    if binary is None:
        pytest.skip('Godot 4 unavailable')
    root = Path(__file__).resolve().parents[1]
    assert (root/'godot/notation/native/connector_geometry.gd').exists(), 'Independent connector geometry is missing'
    run = subprocess.run([binary,'--headless','--path',str(root/'godot'),
        '--script',str(root/'tests/godot/native_connector_geometry.gd')],
        capture_output=True,text=True,timeout=30)
    output = run.stdout+run.stderr
    assert run.returncode == 0 and 'SCRIPT ERROR' not in output, output
    assert 'CONNECTOR_GEOMETRY_FAILURES:0' in output, output

"""A zero Godot exit code cannot hide emitted parse diagnostics in CI."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT/'scripts/check_godot_parse.py'


@pytest.mark.parametrize('message,exit_code,passed', [
    ('Godot Engine: scripts valid', 0, True),
    ('SCRIPT ERROR: Parse Error at res://broken.gd:12', 0, False),
    ('ERROR: Failed to load script res://missing.gd', 0, False),
    ('driver startup failed', 3, False),
])
def test_parse_gate_checks_diagnostics_and_process_status(tmp_path, message, exit_code, passed):
    binary = tmp_path/'godot'
    binary.write_text('#!'+sys.executable+'\nimport sys\n'
                      f'print({message!r}, file=sys.stderr)\nsys.exit({exit_code})\n')
    binary.chmod(0o755)
    result = subprocess.run([sys.executable,str(GATE),'--godot',str(binary),
                             '--project',str(ROOT/'godot'),'--script','res://main.gd'],
                            capture_output=True,text=True,timeout=5)
    assert (result.returncode == 0) == passed, result.stdout+result.stderr
    assert message in result.stdout+result.stderr
    if exit_code:
        assert result.returncode == exit_code


def test_parse_gate_bounds_an_unresponsive_engine(tmp_path):
    binary = tmp_path/'godot'
    binary.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(5)\n')
    binary.chmod(0o755)
    result = subprocess.run([sys.executable,str(GATE),'--godot',str(binary),
                             '--project',str(ROOT/'godot'),'--script','res://main.gd',
                             '--timeout','.05'],capture_output=True,text=True,timeout=3)
    assert result.returncode == 124 and 'timed out' in (result.stdout+result.stderr).lower()

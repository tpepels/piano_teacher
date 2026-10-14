"""Exercise Godot's actual GDScript parser when it is installed.

Python unit tests alone cannot detect undeclared GDScript identifiers.
This check catches editor parse errors even on a headless Linux runner.
"""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


def test_moving_score_does_not_reference_undeclared_scroll_state():
    source = (ROOT / "godot" / "main.gd").read_text(encoding="utf-8")
    # A named scroll target is fine once declared; assignment without
    # declaration caused the original fullscreen grey-screen regression.
    assignments = [line for line in source.splitlines()
                   if line.strip().startswith("scroll_target_x =")]
    declarations = [line for line in source.splitlines()
                    if line.strip().startswith("var scroll_target_x")]
    assert not assignments or declarations


@pytest.mark.skipif(GODOT is None, reason="Godot 4 binary is not installed")
def test_godot_script_parses_headlessly():
    completed = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--check-only", "--script", "res://main.gd"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )
    output = completed.stdout
    assert completed.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "Parse Error:" not in output, output

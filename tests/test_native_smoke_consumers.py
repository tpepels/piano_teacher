"""Focused CLI contracts; never launch Godot or bind the application port."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def invoke_checker(name, *args):
    env = dict(os.environ)
    env.pop("PIANO_TEACHER_NATIVE_NOTATION", None)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT), env.get("PYTHONPATH"))))
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)


def test_compatibility_checker_exposes_canonical_options_without_selector():
    result = invoke_checker("check_native_notation.py", "--help")
    assert result.returncode == 0, result.stderr
    for option in ("--out", "--only", "--case", "--window-bars"):
        assert option in result.stdout
    assert "PIANO_TEACHER_NATIVE_NOTATION" not in result.stdout


def test_compatibility_checker_preserves_canonical_parser_failure():
    result = invoke_checker("check_native_notation.py", "--window-bars", "invalid")
    canonical = invoke_checker("check_native_verovio_overlay.py", "--window-bars", "invalid")
    assert result.returncode == canonical.returncode == 2
    assert "invalid int value" in result.stderr


def test_compatibility_main_accepts_explicit_argv_and_restores_process_args(capsys):
    from scripts.check_native_notation import main

    previous = sys.argv
    with pytest.raises(SystemExit) as error:
        main(["--window-bars", "invalid"])
    assert error.value.code == 2
    assert "invalid int value" in capsys.readouterr().err
    assert sys.argv is previous


@pytest.mark.parametrize("selector", [None, "0", "1"])
def test_native_smoke_needs_godot_without_renderer_selection(monkeypatch, capsys, selector):
    from scripts import smoke_native_notation

    if selector is None:
        monkeypatch.delenv("PIANO_TEACHER_NATIVE_NOTATION", raising=False)
    else:
        monkeypatch.setenv("PIANO_TEACHER_NATIVE_NOTATION", selector)
    monkeypatch.setattr(smoke_native_notation.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit) as error:
        smoke_native_notation.main([])
    assert error.value.code == 2
    assert "Godot 4 is required" in capsys.readouterr().err

"""The package entry point launches the same Godot product as run.sh."""
from pathlib import Path
import os
import runpy
import shutil
import subprocess
import sys
import tomllib
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_module_executes_existing_godot_launcher_and_forwards_arguments(monkeypatch):
    calls = []

    class Launched(Exception):
        pass

    def exec_launcher(path, arguments):
        calls.append((path, arguments))
        raise Launched

    def qt_launch():
        calls.append("qt")
        raise Launched

    monkeypatch.setattr("os.execv", exec_launcher)
    monkeypatch.setitem(sys.modules, "piano_teacher.ui", types.SimpleNamespace(main=qt_launch))
    monkeypatch.setattr(sys, "argv", ["piano_teacher", "--", "--phase0-smoke"])
    with pytest.raises(Launched):
        runpy.run_module("piano_teacher", run_name="__main__")
    launcher = str(ROOT / "run.sh")
    assert calls == [(launcher, [launcher, "--", "--phase0-smoke"])]


def test_public_package_scripts_keep_server_and_retire_qt():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["piano-teacher"] == "piano_teacher.server:main"
    assert "piano-teacher-qt" not in scripts


def test_installed_module_without_godot_assets_reports_checkout_requirement(tmp_path):
    package = tmp_path / "site-packages" / "piano_teacher"
    package.mkdir(parents=True)
    for filename in ("__init__.py", "__main__.py"):
        shutil.copyfile(ROOT / "piano_teacher" / filename, package / filename)
    result = subprocess.run(
        [sys.executable, "-S", "-m", "piano_teacher"], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(package.parent)},
        capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "native Godot application requires a project checkout" in result.stderr
    assert "Traceback" not in result.stderr and "Qt" not in result.stderr

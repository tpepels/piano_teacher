"""Guard the current-application test scope gate against silent omissions."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _scope(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "piano_teacher_ci_scope", ROOT / "scripts" / "ci-scope.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path
    module.TESTS = tmp_path / "tests"
    module.REGISTRY = module.TESTS / "ci-scope.json"
    (module.TESTS / "godot").mkdir(parents=True)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "piano_teacher").mkdir(parents=True)
    (module.TESTS / "test_current.py").write_text(
        "def test_current():\n    assert True\n"
    )
    (module.TESTS / "godot" / "native_current.gd").write_text(
        "extends SceneTree\nfunc _initialize() -> void:\n    quit()\n"
    )
    (tmp_path / ".github" / "workflows" / "current.yml").write_text(
        "name: current\non: push\njobs: {}\n"
    )
    (tmp_path / "piano_teacher" / "runtime.py").write_text("ACTIVE = True\n")
    return module


def _registry(scope, exclude=()):
    entries = {
        scope.rel(path): {
            "owner": "piano_teacher/runtime.py",
            "contract": "Current embedded practice runtime contract",
        }
        for path in scope.modules() if scope.rel(path) not in exclude
    }
    scope.REGISTRY.write_text(json.dumps({"schema": 1, "modules": entries}))


def test_scope_registry_covers_pytest_godot_harness_and_workflow(tmp_path):
    scope = _scope(tmp_path)
    assert {scope.rel(p) for p in scope.modules()} == {
        "tests/test_current.py",
        "tests/godot/native_current.gd",
        ".github/workflows/current.yml",
    }
    _registry(scope)
    assert scope.verify() == 0


def test_scope_registry_rejects_missing_native_harness(tmp_path, capsys):
    scope = _scope(tmp_path)
    _registry(scope, exclude={"tests/godot/native_current.gd"})
    assert scope.verify() != 0
    assert "unreviewed" in capsys.readouterr().err


def test_scope_registry_rejects_missing_workflow(tmp_path, capsys):
    scope = _scope(tmp_path)
    _registry(scope, exclude={".github/workflows/current.yml"})
    assert scope.verify() != 0
    assert "unreviewed" in capsys.readouterr().err


def test_scope_registry_rejects_removed_owner_and_quarantine(tmp_path):
    scope = _scope(tmp_path)
    _registry(scope)
    assert scope.verify(require_no_quarantine=True) == 0
    (scope.TESTS / "quarantine.txt").write_text(
        "tests/test_current.py::test_current | still failing\n"
    )
    assert scope.verify(require_no_quarantine=True) != 0
    (scope.TESTS / "quarantine.txt").unlink()
    (tmp_path / "piano_teacher" / "runtime.py").unlink()
    assert scope.verify() != 0

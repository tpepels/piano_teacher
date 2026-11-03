"""Developer launcher rebuilds stale C++ and verifies changed Python/Godot."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/dev_runtime_state.py"
spec = importlib.util.spec_from_file_location("dev_runtime_state", SCRIPT)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def _checkout(tmp_path):
    root = tmp_path / "project"
    for rel in (*runtime.NATIVE_INPUTS, Path("native/src/piano_native.cpp"),
                *runtime.RUNTIME_FILES, runtime.BINARY, runtime.MANIFEST,
                runtime.ABI_FILE, Path("piano_teacher/inprocess.py"),
                Path("godot/main.gd")):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(rel))
    (root / runtime.BINARY).write_bytes(b"compiled bridge")
    (root / runtime.ABI_FILE).write_text(
        f"{sys.version_info.major}.{sys.version_info.minor}")
    godot = root / "godot-executable"
    godot.write_bytes(b"fake editor")
    return root, godot


def test_native_rebuild_checks_inputs_abi_and_binary(tmp_path, monkeypatch):
    root, _godot = _checkout(tmp_path)
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "x86_64")
    assert not runtime.check_native(root)
    runtime.record_native(root)
    assert runtime.check_native(root)
    (root / "piano_teacher/inprocess.py").write_text("changed Python")
    (root / "godot/main.gd").write_text("changed UI")
    assert runtime.check_native(root)
    (root / "native/src/piano_native.cpp").write_text("changed C++")
    assert not runtime.check_native(root)
    runtime.record_native(root)
    (root / runtime.BINARY).write_bytes(b"tampered binary")
    assert not runtime.check_native(root)


def test_runtime_smoke_changes_on_python_godot_or_packages(tmp_path, monkeypatch):
    root, godot = _checkout(tmp_path)
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "x86_64")
    runtime.record_native(root)
    before = runtime.runtime_signature(godot, root)
    assert before == runtime.runtime_signature(godot, root)
    (root / "piano_teacher/inprocess.py").write_text("changed Python")
    changed = runtime.runtime_signature(godot, root)
    assert changed != before
    (root / "godot/main.gd").write_text("changed scene")
    changed_ui = runtime.runtime_signature(godot, root)
    assert changed_ui != changed
    monkeypatch.setattr(runtime.metadata, "version", lambda _: "changed-version")
    assert runtime.runtime_signature(godot, root) != changed_ui


def test_launcher_has_native_auto_build_and_source_smoke():
    launcher = (ROOT / "run.sh").read_text()
    build = (ROOT / "scripts/build-inprocess.sh").read_text()
    assert "scripts/dev_runtime_state.py check-native" in launcher
    assert "bash scripts/build-inprocess.sh" in launcher
    assert "scripts/dev_runtime_state.py runtime-signature" in launcher
    assert "bash scripts/verify-native-bridge.sh" in launcher
    assert "piano-native-runtime-sha256" in launcher
    assert "scripts/dev_runtime_state.py record-native" in build

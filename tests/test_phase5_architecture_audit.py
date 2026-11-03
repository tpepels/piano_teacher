"""Phase 5 import-graph and release-content checks."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "phase5_architecture_audit", ROOT / "scripts/verify-phase5-architecture.py")
assert spec is not None and spec.loader is not None
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)


def test_all_product_relative_imports_exist_and_compatibility_paths_are_absent():
    assert auditor.audit_tree(ROOT) == []


def test_missing_relative_import_fails_closed(tmp_path):
    pkg = tmp_path / "piano_teacher"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "broken.py").write_text("from .deleted_module import Other\n")
    errors = auditor.audit_tree(tmp_path)
    assert any("missing relative import piano_teacher.deleted_module" in x
               for x in errors)


def test_release_audit_rejects_editor_server_and_missing_native_assets(tmp_path):
    pkg = tmp_path / "piano_teacher"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    godot = tmp_path / "godot"
    godot.mkdir()
    (godot / "project.godot").write_text('MCPRuntimeServer="obsolete"')
    errors = auditor.audit_tree(tmp_path, package=True)
    assert any("MCPRuntimeServer" not in x and "development-only runtime" in x
               for x in errors)
    assert any("Package missing required asset" in x for x in errors)

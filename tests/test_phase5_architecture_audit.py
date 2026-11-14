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


def test_release_audit_rejects_development_only_godot_scripts(tmp_path):
    pkg = tmp_path / "piano_teacher"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    godot = tmp_path / "godot"
    godot.mkdir()
    (godot / "production_ui_smoke.gd").write_text("extends SceneTree\\n")
    (godot / "production_ui_smoke.gd.uid").write_text("uid://test\\n")
    (godot / "production_session_journey.gd").write_text("extends SceneTree\\n")
    (godot / "tests").mkdir()
    errors = auditor.audit_tree(tmp_path, package=True)
    assert any("developer-only Godot fixture: godot/production_ui_smoke.gd"
               in message for message in errors)
    assert any("developer-only Godot fixture: godot/tests"
               in message for message in errors)
    assert any("developer-only Godot fixture: godot/production_session_journey.gd"
               in message for message in errors)
    assert any("developer-only Godot UID: godot/production_ui_smoke.gd.uid"
               in message for message in errors)


def test_release_audit_rejects_developer_midi_and_mcp_configuration(tmp_path):
    source = tmp_path / "piano_teacher"
    source.mkdir()
    (source / "__init__.py").write_text("")
    midi = tmp_path / "midi"
    midi.mkdir()
    (midi / "demo.mid").write_bytes(b"development fixture")
    godot = tmp_path / "godot"
    godot.mkdir()
    (godot / ".mcp.json").write_text('{"mcpServers": {}}')
    errors = auditor.audit_tree(tmp_path, package=True)
    assert any("developer MIDI repertoire" in issue for issue in errors)
    assert any("development-only MCP configuration" in issue for issue in errors)


def test_release_audit_accepts_only_compiled_runtime_imports(tmp_path):
    pkg = tmp_path / "piano_teacher"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    import_dir = tmp_path / "godot" / ".godot"
    (import_dir / "imported").mkdir(parents=True)
    (import_dir / "imported" / "voice.oggvorbisstr").write_bytes(b"real binary")
    score = tmp_path / "godot" / "assets" / "countin"
    score.mkdir(parents=True)
    for word in ("ichi", "ni", "san", "shi"):
        (score / f"{word}.ogg").write_bytes(b"recording")
        (score / f"{word}.ogg.import").write_text(
            'path="res://.godot/imported/voice.oggvorbisstr"\n')
    errors = auditor.audit_tree(tmp_path, package=True)
    assert not any("editor cache" in error or "count-in" in error for error in errors)
    (import_dir / "editor").mkdir()
    errors = auditor.audit_tree(tmp_path, package=True)
    assert any("editor cache" in error for error in errors)
    (import_dir / "editor").rmdir()
    (import_dir / "imported" / "voice.oggvorbisstr").unlink()
    errors = auditor.audit_tree(tmp_path, package=True)
    assert any("compiled count-in audio" in error for error in errors)

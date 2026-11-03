"""Fast safeguards against re-adding generated caches and obsolete plans."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "repository_hygiene", ROOT / "scripts/check-repository-hygiene.py")
assert spec is not None and spec.loader is not None
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)


def test_git_index_has_no_generated_files_or_superseded_root_plan():
    assert auditor.audit_repo(ROOT) == []


def test_generated_artifacts_are_rejected_by_policy():
    dirty_paths = [
        "godot/.godot/editor/project_metadata.cfg",
        "godot/.godot/shader_cache/x.cache",
        "piano_teacher/__pycache__/server.cpython-314.pyc",
        "dist/piano-teacher.tar.gz", "build/native.o",
        "NOTATION_RENDERING.md",
    ]
    assert len(auditor.audit_paths(dirty_paths)) == len(dirty_paths)


def test_stable_source_uid_and_historical_evidence_are_preserved():
    allowed = [
        "godot/main.gd.uid",
        "godot/addons/godot_mcp_toolkit/plugin.gd.uid",
        "tests/fixtures/connector_pixels/beam16/native-0.25.png",
        "docs/evidence/continuous-repetition-2026-10-26/fast-ci.log",
        "docs/archive/development/NOTATION_RENDERING-2026-10-19.md",
    ]
    assert auditor.audit_paths(allowed) == []

"""Producer metadata records the actual tracked verification inputs."""
import subprocess

import pytest

from scripts import notation_release_provenance as provenance


@pytest.fixture
def repository(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    git("init", "--quiet")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    path = tmp_path / "scripts" / "oracle.py"
    path.parent.mkdir()
    path.write_text("expected = 1\n")
    git("add", "scripts/oracle.py")
    git("commit", "-m", "fixture", "--quiet")
    monkeypatch.setattr(provenance, "ROOT", tmp_path)
    return path


def test_clean_revision_and_any_oracle_edit_have_different_provenance(repository):
    clean = provenance.current_provenance()
    assert clean["clean"]
    assert len(clean["revision"]) == 40
    repository.write_text("expected = 2\n")
    edited = provenance.current_provenance()
    assert not edited["clean"]
    assert edited["revision"] == clean["revision"]
    assert edited["inputs_sha256"] != clean["inputs_sha256"]


def test_missing_verification_input_becomes_explicit_blocked_provenance(repository):
    repository.unlink()
    result = provenance.current_provenance()
    assert result["clean"] is False
    assert result["errors"]


def test_untracked_verification_code_cannot_be_hidden_from_revision_claim(repository):
    (repository.parent / "uncommitted_oracle.py").write_text("pass\n")
    assert not provenance.current_provenance()["clean"]


def test_generated_godot_editor_cache_does_not_change_verification_inputs(repository):
    before = provenance.current_provenance()
    cache = repository.parents[1] / "godot" / ".godot" / "editor" / "layout.cfg"
    cache.parent.mkdir(parents=True)
    cache.write_text("generated editor state\n")
    assert provenance.current_provenance() == before


def test_unavailable_git_metadata_preserves_an_explicit_blocked_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(provenance, "ROOT", tmp_path)
    result = provenance.current_provenance()
    assert result["clean"] is False
    assert result["revision"] is None
    assert result["inputs_sha256"] is None
    assert result["errors"]


def test_semantic_producer_records_revision_and_verification_input_digest(monkeypatch):
    from scripts import audit_phase3_semantics as semantic
    expected = {"revision": "a" * 40, "inputs_sha256": "b" * 64, "clean": True}
    monkeypatch.setattr(semantic, "current_provenance", lambda: expected)
    report = semantic.audit_source("tests/fixtures/musical_fidelity/xml_pickup.musicxml", source_index=7)
    assert report["provenance"] == expected

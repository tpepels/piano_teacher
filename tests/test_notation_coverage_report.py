"""Fail-closed current-revision coverage artifact for the small source corpus.

The contract is semantic. It must not treat missing pixels or old screenshots
as a measured/current native-notation pass.
"""
from pathlib import Path
from unittest.mock import patch
import json

from scripts import audit_notation_proof as audit


def test_supported_source_inventory_is_exact_and_nonempty():
    manifest = json.loads((audit.CORPUS/"manifest.json").read_text())
    expected = tuple(row["file"] for row in manifest["supported"]
                     if row["file"].endswith(".musicxml"))
    assert expected and len(expected) >= 8
    assert audit.SOURCES == expected
    assert len(set(expected)) == len(expected)
    assert all((audit.CORPUS/name).is_file() for name in expected)


def test_report_never_calls_semantic_proof_a_visual_pass(tmp_path, monkeypatch):
    records = []

    def source(path):
        records.append(path.name)
        return {"name":path.name, "passed": True,
                "source_sha256": "0"*64,
                "original_source":{"source_attacks":1},
                "verovio_native_contract":{"native_symbols":1}}

    monkeypatch.setattr(audit,"audit_source",source)
    monkeypatch.setattr(audit,"current_provenance",
                        lambda: {"revision":"a"*40,"inputs_sha256":"b"*64,
                                 "clean":True})
    report_file = tmp_path/"coverage.json"
    monkeypatch.setattr("sys.argv",["audit_notation_proof.py","--out",str(report_file)])
    assert audit.main() == 0
    report = json.loads(report_file.read_text())
    assert tuple(records) == audit.SOURCES
    assert report["source_coverage"]["expected"] == len(audit.SOURCES)
    assert report["pinned_manifest_sha256"]
    assert report["passed"] and report["provenance"]["revision"] == "a"*40
    assert report["visual_evidence"]["status"] == "not_run"
    assert report["visual_evidence"]["current_revision_framebuffers"] == 0
    assert report["visual_evidence"]["verified_glyphs"] is None


def test_missing_source_is_counted_and_never_passes(tmp_path, monkeypatch):
    def source(path):
        if path.name == audit.SOURCES[-1]:
            raise OSError("fixture unavailable")
        return {"name":path.name,"passed":True,
                "source_sha256":"0"*64}
    monkeypatch.setattr(audit,"audit_source",source)
    monkeypatch.setattr(audit,"current_provenance",
                        lambda: {"revision":"a"*40,"clean":True})
    report_file = tmp_path/"incomplete.json"
    monkeypatch.setattr("sys.argv",["audit_notation_proof.py","--out",str(report_file)])
    assert audit.main() == 1
    report = json.loads(report_file.read_text())
    assert len(report["scores"]) == len(audit.SOURCES)
    assert report["source_coverage"]["semantically_passed"] == len(audit.SOURCES)-1
    assert not report["passed"]
    assert report["scores"][-1]["errors"] == ["OSError: fixture unavailable"]


def test_unverifiable_revision_cannot_pass_even_when_every_score_does(tmp_path, monkeypatch):
    monkeypatch.setattr(audit,"audit_source",
        lambda path: {"name":path.name,"passed":True,"source_sha256":"0"*64})
    monkeypatch.setattr(audit,"current_provenance",
                        lambda: {"revision":None,"clean":False})
    path = tmp_path/"bad-provenance.json"
    monkeypatch.setattr("sys.argv",["audit_notation_proof.py","--out",str(path)])
    assert audit.main() == 1
    assert not json.loads(path.read_text())["passed"]

"""Release decisions cannot exceed independently accounted evidence."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts import aggregate_phase3_corpus as aggregation
from scripts import audit_native_release as release
from piano_teacher.notation import support_policy
from test_phase3_corpus_aggregation import pinned_test_corpus, _complete, _path

REVISION = "a" * 40


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    _complete(reports, kind="semantic")
    _complete(reports, kind="visual")
    monkeypatch.setattr(release, "current_provenance", lambda: {
        "revision": REVISION, "inputs_sha256": "b" * 64, "clean": True})
    cases = []
    for path in sorted(reports.glob("*/summary.json")):
        data = json.loads(path.read_text())
        data["provenance"] = release.current_provenance()
        path.write_text(json.dumps(data))
        cases.append({**{k: data[k] for k in ("verification_kind", "source_index", "source", "source_sha256", "hand")},
                      "report_sha256": sha256(path.read_bytes()).hexdigest(),
                      "complete": True, "errors": [], "files": []})
    manifest = tmp_path / "evidence" / "evidence-manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"schema_version": 1, "revision": REVISION,
                                   "complete": True, "errors": [], "cases": cases}))
    monkeypatch.setattr(release, "validate_evidence", lambda *args: {"complete": True, "errors": [], "cases": cases})
    monkeypatch.setattr(release, "validate_mutations", lambda *args: {"complete": True, "errors": [], "suites": []})
    monkeypatch.setattr(release, "validate_prerequisites", lambda *args: {"complete": True, "errors": []})
    return reports, manifest, tmp_path / "mutations"


def run(evidence):
    return release.build_report(*evidence, revision=REVISION)


def test_release_keeps_two_independent_categories_and_exact_coverage(evidence):
    report = run(evidence)
    assert report["schema_version"] == 1
    assert report["release_ready"] is True
    assert set(report["categories"]) == {"semantic", "visual"}
    assert report["required_cases"] == 12
    for category in report["categories"].values():
        assert category["complete"]
        coverage = category["coverage"]
        assert coverage["expected"] == coverage["verified"] > 0
        for dimension in ("by_score", "by_hand", "by_measure", "by_feature"):
            assert sum(row["coverage"]["expected"] for row in category[dimension]) == coverage["expected"]


@pytest.mark.parametrize("status", ["ambiguous", "unsupported", "unverified", "mismatch"])
def test_each_nonverified_status_blocks_release_and_retains_source_location(evidence, status):
    reports = evidence[0]
    path = _path(reports, kind="semantic")
    data = json.loads(path.read_text())
    row = data["elements"][-1]
    row["status"] = status
    data["coverage"]["verified"] -= 1
    data["coverage"][status] += 1
    data["complete"] = False
    data["passed"] = status != "mismatch"
    path.write_text(json.dumps(data))
    report = run(evidence)
    assert not report["release_ready"]
    semantic = report["categories"]["semantic"]
    assert semantic["coverage"][status] == 1
    discrepancy = next(r for r in semantic["nonverified_elements"] if r["status"] == status)
    assert discrepancy["source"] == row["source"]
    assert report["categories"]["visual"]["complete"]


def test_missing_report_restores_measure_denominator(evidence):
    before = run(evidence)
    _path(evidence[0], kind="visual").unlink()
    after = run(evidence)
    assert not after["release_ready"]
    assert after["categories"]["visual"]["coverage"]["expected"] == before["categories"]["visual"]["coverage"]["expected"]
    assert after["categories"]["visual"]["coverage"]["unverified"] > 0


def test_malformed_visual_id_yields_a_blocked_report_with_preserved_inventory(evidence):
    before = run(evidence)
    path = _path(evidence[0], kind="visual")
    data = json.loads(path.read_text())
    data["elements"][0]["id"] = []
    path.write_text(json.dumps(data))
    result = run(evidence)
    assert not result["release_ready"]
    assert result["categories"]["visual"]["coverage"]["expected"] >= before["categories"]["visual"]["coverage"]["expected"]


@pytest.mark.parametrize("change", ["revision", "inputs_sha256", "absent"])
def test_reports_from_other_revision_or_oracle_cannot_be_relabelled(evidence, change):
    path = _path(evidence[0], kind="semantic")
    data = json.loads(path.read_text())
    if change == "absent":
        data.pop("provenance")
    else:
        data["provenance"][change] = "c" * (40 if change == "revision" else 64)
    path.write_text(json.dumps(data))
    report = run(evidence)
    assert not report["release_ready"]
    assert any("provenance" in error.lower() for error in report["blockers"])


def test_matching_unavailable_provenance_never_grants_verified_credit(evidence, monkeypatch):
    unavailable = {"revision": None, "inputs_sha256": None, "clean": False, "errors": ["Git unavailable"]}
    monkeypatch.setattr(release, "current_provenance", lambda: unavailable)
    for path in evidence[0].glob("*/summary.json"):
        data = json.loads(path.read_text())
        data["provenance"] = unavailable
        path.write_text(json.dumps(data))
    report = run(evidence)
    assert not report["release_ready"]
    assert report["coverage"]["verified"] == 0
    assert report["coverage"]["unverified"] == report["coverage"]["expected"]


def test_failed_mutations_or_missing_artifacts_cannot_be_overridden_by_manual_review(evidence, monkeypatch):
    monkeypatch.setattr(release, "validate_mutations", lambda *args: {"complete": False, "errors": ["Skipped mutation"], "suites": []})
    result = release.build_report(*evidence, revision=REVISION,
                                  manual_review={"approved": True, "reviewer": "editor"})
    assert not result["release_ready"]
    assert result["manual_review"]["affects_automated_decision"] is False
    assert "Skipped mutation" in result["blockers"]


def test_phase2_actual_rendering_is_a_required_independent_release_prerequisite(evidence, monkeypatch):
    monkeypatch.setattr(release, "validate_prerequisites", lambda *args: {
        "complete": False, "errors": ["Phase 2 actual native screenshot evidence failed"]})
    result = run(evidence)
    assert not result["release_ready"]
    assert result["prior_phases"]["complete"] is False


def test_normalized_ledger_is_exposed_by_existing_aggregator(evidence):
    result = aggregation.aggregate(evidence[0], scores=2, include_elements=True)
    assert sum(len(job["elements"]) for job in result["jobs"]) == result["coverage"]["expected"]


def test_release_uses_supported_scope_without_claiming_complete_coverage(evidence, monkeypatch):
    aggregate = aggregation.aggregate(evidence[0], scores=2, include_elements=True,
                                      required_provenance=release.current_provenance())
    job = aggregate["jobs"][0]
    job["elements"][-1]["status"] = "unsupported"
    job["coverage"]["verified"] -= 1
    job["coverage"]["unsupported"] += 1
    job["complete"] = False
    aggregate["coverage"]["verified"] -= 1
    aggregate["coverage"]["unsupported"] += 1
    aggregate.update(complete=False, passed=False, errors=["Incomplete authorial notation"],
                     coverage_errors=["Incomplete authorial notation"])
    # This test isolates release integration. Exact MIDI classification and rule
    # proof/replay have separate adversarial tests and cannot be overridden by
    # producer fields in production.
    scope = support_policy.assess_jobs(aggregate["jobs"])
    scope.update(passed=True, blockers=[], limitations=[{"reason_code": "test_source_limitation"}])
    monkeypatch.setattr(aggregation, "aggregate", lambda *args, **kwargs: aggregate)
    monkeypatch.setattr(support_policy, "assess_jobs", lambda jobs: scope)
    result = run(evidence)
    assert result["release_ready"] is True
    assert result["verification_complete"] is False
    assert result["categories"]["semantic"]["complete"] is False
    assert result["coverage"]["unsupported"] == 1
    assert result["supported_scope"]["limitations"] == scope["limitations"]


def test_supported_scope_never_overrides_missing_inventory_or_artifact_integrity(evidence, monkeypatch):
    _path(evidence[0], kind="semantic").unlink()
    monkeypatch.setattr(support_policy, "assess_jobs", lambda jobs: {
        "passed": True, "complete": True, "blockers": [], "limitations": []})
    assert not run(evidence)["release_ready"]


def test_semantic_producer_records_revision_and_verification_input_digest(monkeypatch):
    from scripts import audit_phase3_semantics as semantic
    expected = {"revision": REVISION, "inputs_sha256": "b" * 64, "clean": True}
    monkeypatch.setattr(semantic, "current_provenance", lambda: expected)
    report = semantic.audit_source("tests/fixtures/musical_fidelity/xml_pickup.musicxml", source_index=7)
    assert report["provenance"] == expected


@pytest.fixture
def mutation_evidence(tmp_path, monkeypatch):
    files = ("tests/test_detector.py",)
    file = tmp_path / files[0]
    file.parent.mkdir()
    file.write_text("def test_detector(): pass\n")
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "current_provenance", lambda: {
        "revision": REVISION, "inputs_sha256": "b" * 64, "clean": True})
    monkeypatch.setitem(sys.modules, "scripts.record_notation_mutations", SimpleNamespace(SUITES={"semantic": files}))
    monkeypatch.setattr(release, "_expected_nodeids", lambda files: ["tests/test_detector.py::test_detector"])
    folder = tmp_path / "mutations" / "semantic"
    folder.mkdir(parents=True)
    junit = folder / "results.xml"
    junit.write_text('<testsuites><testsuite tests="1"><testcase classname="tests.test_detector" name="test_detector"/></testsuite></testsuites>')
    manifest = folder / "suite.json"
    manifest.write_text(json.dumps({"schema_version": 1, "revision": REVISION, "suite": "semantic",
        "provenance": release.current_provenance(), "provenance_after": release.current_provenance(),
        "junit_path": junit.name, "junit_sha256": sha256(junit.read_bytes()).hexdigest(),
        "expected_nodeids": ["tests/test_detector.py::test_detector"],
        "test_files_sha256": {files[0]: sha256(file.read_bytes()).hexdigest()}}))
    return folder.parent, manifest, junit


def test_actual_complete_mutation_execution_is_required(mutation_evidence):
    assert release.validate_mutations(mutation_evidence[0], REVISION)["complete"]


@pytest.mark.parametrize("mutation", ["skipped", "failure", "error", "absent", "duplicate", "revision", "test_hash", "junit_hash", "expected_subset", "declared_failure", "declared_tests", "bad_counter", "dirty_execution", "different_inputs", "changed_during_tests", "absent_provenance"])
def test_mutation_record_cannot_hide_missing_failed_or_stale_tests(mutation_evidence, mutation):
    folder, manifest, junit = mutation_evidence
    data = json.loads(manifest.read_text())
    if mutation in ("skipped", "failure", "error"):
        junit.write_text(junit.read_text().replace("/>", f"><{mutation}/></testcase>"))
    elif mutation == "absent":
        junit.write_text('<testsuites><testsuite tests="0"/></testsuites>')
    elif mutation == "duplicate":
        junit.write_text(junit.read_text().replace("</testsuite>", '<testcase classname="tests.test_detector" name="test_detector"/></testsuite>'))
    elif mutation == "revision":
        data["revision"] = "c" * 40
    elif mutation == "test_hash":
        data["test_files_sha256"] = {}
    elif mutation == "expected_subset":
        data["expected_nodeids"] = []
    elif mutation == "declared_failure":
        junit.write_text(junit.read_text().replace('tests="1"', 'tests="1" failures="1"'))
    elif mutation == "declared_tests":
        junit.write_text(junit.read_text().replace('tests="1"', 'tests="2"'))
    elif mutation == "bad_counter":
        junit.write_text(junit.read_text().replace('tests="1"', 'tests="NaN"'))
    elif mutation == "dirty_execution":
        data["provenance"]["clean"] = False
    elif mutation == "different_inputs":
        data["provenance"]["inputs_sha256"] = "c" * 64
    elif mutation == "changed_during_tests":
        data["provenance_after"]["inputs_sha256"] = "c" * 64
    elif mutation == "absent_provenance":
        data.pop("provenance")
    if mutation != "junit_hash":
        data["junit_sha256"] = sha256(junit.read_bytes()).hexdigest()
    else:
        data["junit_sha256"] = "c" * 64
    manifest.write_text(json.dumps(data))
    result = release.validate_mutations(folder, REVISION)
    assert not result["complete"]
    assert result["errors"]

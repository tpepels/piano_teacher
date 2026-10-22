"""Contracts for revision-bound CI, diagnostic artifacts and gated releases."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
REVISION = "a" * 40


def test_container_provenance_uses_an_explicit_exact_workspace_trust_step():
    for filename in ("phase3-corpus.yml", "phase3-whole-piece.yml", "pixel-proof.yml"):
        for job in workflow(filename)["jobs"].values():
            if "container" not in job:
                continue
            steps = job["steps"]
            checkout = next(i for i, step in enumerate(steps) if step.get("uses", "").startswith("actions/checkout@"))
            command = 'git config --global --add safe.directory "$GITHUB_WORKSPACE"'
            assert steps[checkout + 1].get("run") == command
SEMANTIC_FILES = (
    "tests/test_notation_proof_phase1.py",
    "tests/test_phase3_semantics.py",
    "tests/test_phase3_corpus_aggregation.py",
)
PHASE2_FILES = {
    "tests/test_native_pixel_proof.py",
    "tests/test_source_beam_pixel_fidelity.py",
    "tests/test_native_symbol_pixel_proof.py",
}


def recorder():
    path = ROOT / "scripts/record_notation_mutations.py"
    assert path.is_file(), "mutation suites need a trusted collection/recording entrypoint"
    spec = importlib.util.spec_from_file_location("mutation_recorder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mutation_registry_covers_prior_detectors_and_all_phase4_contracts():
    suites = recorder().SUITES
    assert set(suites) == {"semantic", "visual", "real_rest", "release_contract"}
    assert suites["semantic"] == SEMANTIC_FILES
    assert PHASE2_FILES <= set(suites["visual"])
    assert "tests/test_phase3_real_rest_protocol.py" in suites["real_rest"]
    assert set(suites["release_contract"]) == {
        str(path.relative_to(ROOT)) for path in ROOT.glob("tests/test_phase4_*.py")
    }
    assert all(isinstance(files, tuple) and files for files in suites.values())
    all_files = [path for files in suites.values() for path in files]
    assert len(all_files) == len(set(all_files)), "detector files must run once per gate"


def mutation_fixture(tmp_path, body):
    script = ROOT / "scripts/record_notation_mutations.py"
    assert script.is_file(), "mutation recording must exist before executing suites"
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(script, tmp_path / "scripts" / script.name)
    shutil.copyfile(ROOT / "scripts/notation_release_provenance.py",
                    tmp_path / "scripts/notation_release_provenance.py")
    (tmp_path / "tests").mkdir()
    for index, path in enumerate(SEMANTIC_FILES):
        (tmp_path / path).write_text(body if index == 0 else "def test_ok(): pass\n")
    (tmp_path / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (tmp_path / "pyproject.toml").write_text("# tracked application input\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                    "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    return tmp_path / "scripts" / script.name


def run_recorder(tmp_path, body, *extra):
    script = mutation_fixture(tmp_path, body)
    out = tmp_path / "evidence" / "semantic"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    result = subprocess.run(
        [sys.executable, str(script), "--suite", "semantic", "--revision", revision,
         "--out", str(out), *extra], cwd=tmp_path, text=True, capture_output=True,
        env={**os.environ, "REGISTRY": str(out / "suite.json"), "PYTEST_ADDOPTS": ""},
        timeout=60,
    )
    return result, out


def test_recorder_collects_parametrizations_before_running_and_hashes_actual_junit(tmp_path):
    result, out = run_recorder(tmp_path, '''
import json, os
from pathlib import Path
import pytest
@pytest.mark.parametrize("value", ["a.b", "x[y]"])
def test_case(value):
    manifest = json.loads(Path(os.environ["REGISTRY"]).read_text())
    assert len(manifest["expected_nodeids"]) == 4
    assert manifest["junit_sha256"] is None
    assert manifest["provenance"]["clean"] is True
    assert manifest["provenance_after"] is None
''')
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((out / "suite.json").read_text())
    assert set(manifest) == {"schema_version", "revision", "suite", "junit_path",
                             "junit_sha256", "expected_nodeids", "test_files_sha256",
                             "provenance", "provenance_after"}
    assert manifest["schema_version"] == 1
    assert manifest["revision"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    assert manifest["provenance"] == manifest["provenance_after"]
    assert manifest["provenance"]["clean"] is True
    assert manifest["provenance"]["revision"] == manifest["revision"]
    assert len(manifest["provenance"]["inputs_sha256"]) == 64
    assert manifest["suite"] == "semantic"
    assert manifest["expected_nodeids"] == sorted([
        "tests/test_notation_proof_phase1.py::test_case[a.b]",
        "tests/test_notation_proof_phase1.py::test_case[x[y]]",
        "tests/test_phase3_semantics.py::test_ok",
        "tests/test_phase3_corpus_aggregation.py::test_ok",
    ])
    assert manifest["test_files_sha256"] == {
        name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        for name in SEMANTIC_FILES
    }
    junit = out / manifest["junit_path"]
    assert manifest["junit_sha256"] == hashlib.sha256(junit.read_bytes()).hexdigest()
    assert len(ET.parse(junit).findall(".//testcase")) == 4


@pytest.mark.parametrize("body", [
    "def test_bad(): assert False\n",
    "import pytest\n@pytest.mark.skip(reason='disabled')\ndef test_bad(): pass\n",
    "import pytest\n@pytest.fixture\ndef broken(): raise RuntimeError('error')\ndef test_bad(broken): pass\n",
    "import pytest\n@pytest.mark.xfail(reason='known')\ndef test_bad(): assert False\n",
])
def test_recorder_preserves_failed_or_skipped_raw_evidence_and_blocks(tmp_path, body):
    result, out = run_recorder(tmp_path, body)
    assert result.returncode == 1, result.stdout + result.stderr
    manifest = json.loads((out / "suite.json").read_text())
    junit = out / manifest["junit_path"]
    assert junit.is_file()
    assert manifest["junit_sha256"] == hashlib.sha256(junit.read_bytes()).hexdigest()
    assert len(manifest["expected_nodeids"]) == 3


def test_collection_failure_still_records_blocked_suite_and_does_not_execute_tests(tmp_path):
    result, out = run_recorder(tmp_path, "raise RuntimeError('broken collection')\n")
    assert result.returncode == 1
    manifest = json.loads((out / "suite.json").read_text())
    assert manifest["expected_nodeids"] == []
    assert manifest["junit_sha256"] is None
    assert not (out / manifest["junit_path"]).exists()
    assert (out / "collection.log").is_file()


def test_mutating_application_during_tests_leaves_evidence_but_blocks_execution_provenance(tmp_path):
    result, out = run_recorder(tmp_path, '''
from pathlib import Path
def test_changes_application():
    Path("pyproject.toml").write_text("# modified application\\n")
''')
    assert result.returncode == 1, result.stdout + result.stderr
    manifest = json.loads((out / "suite.json").read_text())
    assert manifest["provenance"]["clean"] is True
    assert manifest["provenance_after"]["clean"] is False
    assert manifest["provenance_after"]["inputs_sha256"] != manifest["provenance"]["inputs_sha256"]
    assert (out / manifest["junit_path"]).exists()


def test_mutations_cannot_start_against_an_edited_application_even_if_revision_matches(tmp_path):
    script = mutation_fixture(tmp_path, "def test_ok(): pass\n")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    (tmp_path / "pyproject.toml").write_text("# edited application\n")
    out = tmp_path / "evidence/semantic"
    result = subprocess.run([sys.executable, str(script), "--suite", "semantic",
                             "--revision", revision, "--out", str(out)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 1, result.stdout + result.stderr
    manifest = json.loads((out / "suite.json").read_text())
    assert manifest["provenance"]["clean"] is False
    assert manifest["junit_sha256"] is None
    assert not (out / manifest["junit_path"]).exists()


@pytest.mark.parametrize("revision", ["main", "a" * 7, "z" * 40, ""])
def test_recorder_rejects_nonimmutable_revisions(tmp_path, revision):
    script = mutation_fixture(tmp_path, "def test_ok(): pass\n")
    result = subprocess.run(
        [sys.executable, str(script), "--suite", "semantic", "--revision", revision,
         "--out", str(tmp_path / "out")], capture_output=True, text=True,
    )
    assert result.returncode != 0


def workflow(name):
    path = ROOT / ".github/workflows" / name
    assert path.is_file(), f"missing workflow: {name}"
    # BaseLoader leaves GitHub's `on` key and expressions as strings.
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader)


def steps_using(job, action):
    return [step for step in job.get("steps", []) if step.get("uses", "").startswith(action + "@")]


def test_phase3_corpus_is_reusable_and_runs_the_51_visual_cases_only_once():
    corpus = workflow("phase3-corpus.yml")
    assert set(corpus["on"]) == {"workflow_call"}
    assert corpus["on"]["workflow_call"]["inputs"]["revision"]["required"] == "true"
    jobs = corpus["jobs"]
    matrix = jobs["visual-scores"]["strategy"]["matrix"]
    assert matrix["index"] == [str(i) for i in range(17)]
    assert matrix["hand"] == ["both", "right", "left"]
    assert jobs["visual-scores"]["strategy"]["fail-fast"] == "false"
    audit_steps = [step for job in jobs.values() for step in job.get("steps", [])
                   if "audit_phase3_whole_pieces.py" in step.get("run", "")]
    assert len(audit_steps) == 1
    assert "--allow-incomplete" not in audit_steps[0]["run"]
    assert corpus["on"]["workflow_call"]["outputs"]["revision"]["value"]
    for job in jobs.values():
        for checkout in steps_using(job, "actions/checkout"):
            assert checkout["with"]["ref"] == "${{ inputs.revision }}"
        for upload in steps_using(job, "actions/upload-artifact"):
            assert upload["if"] == "always()"
            assert int(upload["with"]["retention-days"]) >= 30
    for name in ("semantic-corpus-gate", "visual-corpus-gate", "whole-corpus-gate"):
        assert jobs[name]["if"] == "always()"
        checks = [step for step in jobs[name]["steps"] if "aggregate_phase3_corpus.py" in step.get("run", "")]
        assert len(checks) == 1
        assert checks[0]["if"] == "always()"
        assert checks[0].get("continue-on-error", "false") == "false"


def test_phase3_mutations_are_reusable_and_all_four_suites_publish_even_on_failure():
    mutations = workflow("phase3-whole-piece.yml")
    assert set(mutations["on"]) == {"workflow_call"}
    all_runs = "\n".join(step.get("run", "") for job in mutations["jobs"].values()
                         for step in job.get("steps", []))
    assert "python -m pytest" not in all_runs, "suite recorder must own collection and execution"
    for suite in ("semantic", "visual", "real_rest", "release_contract"):
        matching = [(job, step) for job in mutations["jobs"].values() for step in job.get("steps", [])
                    if f"--suite {suite}" in step.get("run", "")]
        assert len(matching) == 1, f"{suite} must execute once"
        job, run = matching[0]
        assert "record_notation_mutations.py" in run["run"]
        assert "--revision" in run["run"]
        uploads = steps_using(job, "actions/upload-artifact")
        assert any(step["if"] == "always()" and step["with"]["name"] == f"notation-mutations-{suite}"
                   and int(step["with"]["retention-days"]) >= 30 for step in uploads)
        if suite == "real_rest":
            assert run["env"]["PIANO_REAL_PIXEL_TESTS"] == "1"
            assert "xvfb-run" in run["run"]


def test_phase4_ci_calls_the_same_gate_as_native_release_without_duplicate_corpus():
    ci = workflow("phase4.yml")
    release = workflow("native-release.yml")
    assert set(ci["on"]) == {"pull_request", "push"}
    assert ci["on"]["push"]["branches"] == ["main"]
    ci_gate = ci["jobs"]["exact-release-gate"]
    release_gate = release["jobs"]["exact-release-gate"]
    assert ci_gate["uses"] == release_gate["uses"] == "./.github/workflows/native-release-gate.yml"
    assert ci_gate["with"]["revision"] == "${{ github.sha }}"
    gate = workflow("native-release-gate.yml")
    calls = [job["uses"] for job in gate["jobs"].values() if "uses" in job]
    assert sorted(calls) == ["./.github/workflows/phase3-corpus.yml", "./.github/workflows/phase3-whole-piece.yml",
                             "./.github/workflows/pixel-proof.yml"]
    assert set(gate["on"]) == {"workflow_call"}
    for name in ("corpus", "mutations", "phase2"):
        assert gate["jobs"][name]["needs"] == "validate-revision"


def test_phase4_report_attempts_all_evidence_and_publishes_diagnostics_before_strict_gate():
    jobs = workflow("native-release-gate.yml")["jobs"]
    report = jobs["report-and-package"]
    assert set(report["needs"]) == {"corpus", "mutations", "phase2"}
    assert report["if"] == "always()"
    downloads = steps_using(report, "actions/download-artifact")
    patterns = {step["with"].get("pattern", step["with"].get("name")) for step in downloads}
    assert {"phase3-semantic-reports", "phase3-report-*", "phase3-visual-score-*", "notation-mutations-*",
            "phase2-native-pixel-proof", "phase2-symbol-specimens"} <= patterns
    assert all(step["if"] == "always()" for step in downloads)
    assert all("run-id" not in step["with"] for step in downloads), "evidence must come from this run"
    commands = [step for step in report["steps"] if "run" in step]
    package = next(step for step in commands if "scripts/package_notation_evidence.py" in step["run"])
    audit = next(step for step in commands if "scripts/audit_native_release.py" in step["run"])
    assert package["if"] == audit["if"] == "always()"
    assert commands.index(package) < commands.index(audit)
    assert "--raw" in package["run"] and "--revision" in package["run"]
    for option in ("--reports", "--evidence", "--mutations", "--prerequisites", "--revision", "--out", "--markdown"):
        assert option in audit["run"]
    uploads = steps_using(report, "actions/upload-artifact")
    assert uploads and all(step["if"] == "always()" for step in uploads)
    assert all(int(step["with"]["retention-days"]) >= 30 for step in uploads)
    evidence_upload = next(step for step in uploads if step["with"]["name"] == "phase4-native-release-evidence")
    assert set(evidence_upload["with"]["path"].split()) == {
        "/tmp/phase4/evidence/", "/tmp/phase4/mutations/",
        "/tmp/phase4/prior-phases/",
        "/tmp/phase4/native-release.json", "/tmp/phase4/native-release.md",
    }, "upload the packaged raw tree once"
    assert evidence_upload["with"].get("compression-level", "6") == "6"
    final = jobs["release-gate"]
    assert final["if"] == "always()"
    assert set(final["needs"]) == {"corpus", "mutations", "phase2", "report-and-package"}
    assert "continue-on-error" not in final


def test_semantic_artifact_layout_preserves_full_cases_for_the_packager(tmp_path):
    report = workflow("native-release-gate.yml")["jobs"]["report-and-package"]
    download = next(step for step in steps_using(report, "actions/download-artifact")
                    if step["with"].get("name") == "phase3-semantic-reports")
    assert download["with"]["path"] == "/tmp/phase4/raw"
    case = tmp_path / "raw/phase3-semantic-report-0-both"
    case.mkdir(parents=True)
    (case / "summary.json").write_text('{"provenance":{"revision":"a"}}')
    (case / "generated.musicxml").write_text("<score-partwise/>")
    step = next(step for step in report["steps"] if "Copy all compact semantic" in step.get("name", ""))
    step = {**step, "run": step["run"].replace("/tmp/phase4", str(tmp_path))}
    result = run_workflow_python(step, tmp_path, {})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "reports/phase3-semantic-report-0-both/summary.json").read_bytes() == (case / "summary.json").read_bytes()
    assert (case / "generated.musicxml").exists(), "raw generated models must remain available"


def test_release_tag_and_distribution_cannot_bypass_exact_gate():
    release = workflow("native-release.yml")
    assert release["on"]["push"]["tags"] == ["native-v*"]
    assert set(release["on"]) == {"push", "workflow_dispatch"}
    jobs = release["jobs"]
    for name in ("build-candidate", "publish-draft"):
        job = jobs[name]
        assert "exact-release-gate" in job["needs"]
        assert "needs.exact-release-gate.result == 'success'" in job["if"]
        assert "needs.exact-release-gate.outputs.revision" in job["if"]
        assert "always(" not in job["if"]
        assert "continue-on-error" not in job
        assert all("always(" not in step.get("if", "") and "continue-on-error" not in step
                   for step in job["steps"])
    build = jobs["build-candidate"]
    checkout = steps_using(build, "actions/checkout")[0]
    assert checkout["with"]["ref"] == "${{ needs.exact-release-gate.outputs.revision }}"
    build_runs = "\n".join(step.get("run", "") for step in build["steps"])
    assert "python -m build" in build_runs and "git archive" in build_runs and "godot" in build_runs
    publish_runs = "\n".join(step.get("run", "") for step in jobs["publish-draft"]["steps"])
    assert "gh release create" in publish_runs and "--draft" in publish_runs and "--verify-tag" in publish_runs
    assert jobs["publish-draft"]["permissions"]["contents"] == "write"


def run_workflow_python(step, tmp_path, env):
    script = step["run"]
    assert script.startswith("python - <<'PY'\n") and script.rstrip().endswith("\nPY")
    source = script.split("\n", 1)[1].rsplit("\nPY", 1)[0]
    return subprocess.run([sys.executable, "-c", source], cwd=tmp_path, capture_output=True,
                          text=True, env={**os.environ, **env}, timeout=20)


@pytest.mark.parametrize("key,value", [
    (None, None), ("CORPUS_RESULT", "failure"), ("CORPUS_RESULT", "skipped"),
    ("MUTATIONS_RESULT", "cancelled"), ("REPORT_RESULT", "failure"),
    ("PHASE2_RESULT", "failure"), ("PHASE2_RESULT", "skipped"),
    ("PHASE2_REVISION", "b" * 40),
    ("CORPUS_REVISION", "b" * 40), ("MUTATIONS_REVISION", ""),
    ("EVENT_REVISION", "b" * 40), ("REVISION", "main"),
])
def test_strict_gate_executes_and_blocks_failed_skipped_or_wrong_revision_inputs(tmp_path, key, value):
    gate = workflow("native-release-gate.yml")["jobs"]["release-gate"]
    step = next(s for s in gate["steps"] if s.get("id") == "decision")
    env = dict(REVISION=REVISION, EVENT_REVISION=REVISION,
               CORPUS_RESULT="success", MUTATIONS_RESULT="success", REPORT_RESULT="success",
               CORPUS_REVISION=REVISION, MUTATIONS_REVISION=REVISION,
               PHASE2_RESULT="success", PHASE2_REVISION=REVISION,
               GITHUB_OUTPUT=str(tmp_path / "outputs"))
    if key:
        env[key] = value
    result = run_workflow_python(step, tmp_path, env)
    assert (result.returncode == 0) is (key is None), result.stdout + result.stderr
    if key is None:
        assert (tmp_path / "outputs").read_text() == f"revision={REVISION}\n"
    else:
        assert not (tmp_path / "outputs").exists()


@pytest.mark.parametrize("event,ref_type,ref_name,requested,accepted", [
    ("push", "tag", "native-v1.2.3", "", True),
    ("workflow_dispatch", "tag", "native-v1.2.3", "native-v1.2.3", True),
    ("workflow_dispatch", "branch", "main", "native-v1.2.3", False),
    ("workflow_dispatch", "tag", "native-v1.2.3", "native-v2", False),
    ("push", "tag", "other-v1", "", False),
])
def test_release_context_requires_a_matching_native_tag_at_the_event_sha(
        tmp_path, event, ref_type, ref_name, requested, accepted):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                    "commit", "--allow-empty", "-qm", "fixture"], cwd=tmp_path, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    subprocess.run(["git", "tag", "native-v1.2.3"], cwd=tmp_path, check=True)
    job = workflow("native-release.yml")["jobs"]["release-context"]
    step = next(s for s in job["steps"] if s.get("id") == "tag")
    result = run_workflow_python(step, tmp_path, {
        "EVENT_NAME": event, "REF_TYPE": ref_type, "REF_NAME": ref_name,
        "REQUESTED_TAG": requested, "REVISION": revision,
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
    })
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr


@pytest.mark.parametrize("revision,event_revision,accepted", [
    (REVISION, REVISION, True), ("main", REVISION, False),
    ("a" * 7, REVISION, False), ("b" * 40, REVISION, False),
])
def test_reusable_gate_rejects_branch_inputs_before_audits_but_keeps_reporting(
        tmp_path, revision, event_revision, accepted):
    jobs = workflow("native-release-gate.yml")["jobs"]
    job = jobs["validate-revision"]
    assert not steps_using(job, "actions/checkout"), "validate before checking out untrusted input"
    step = next(s for s in job["steps"] if s.get("id") == "revision")
    result = run_workflow_python(step, tmp_path, {
        "REVISION": revision, "EVENT_REVISION": event_revision,
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
    })
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    report = jobs["report-and-package"]
    assert report["if"] == "always()"
    assert steps_using(report, "actions/checkout")[0]["with"]["ref"] == "${{ github.sha }}"


def test_actual_phase2_baselines_are_reusable_required_and_not_duplicated():
    phase2 = workflow("pixel-proof.yml")
    assert set(phase2["on"]) == {"workflow_call"}
    assert phase2["on"]["workflow_call"]["inputs"]["revision"]["required"] == "true"
    assert phase2["on"]["workflow_call"]["outputs"]["revision"]["value"]
    job = phase2["jobs"]["native-image-pitch"]
    assert steps_using(job, "actions/checkout")[0]["with"]["ref"] == "${{ inputs.revision }}"
    for script in ("check_native_pixels.py", "check_native_symbols.py"):
        matching = [step for step in job["steps"] if f"scripts/{script}" in step.get("run", "")]
        assert len(matching) == 1
        assert matching[0]["if"] == "always()", "both baselines must attempt evidence after a failure"
    assert all("pytest" not in step.get("run", "") for step in job["steps"])
    gate_jobs = workflow("native-release-gate.yml")["jobs"]
    assert gate_jobs["phase2"]["uses"] == "./.github/workflows/pixel-proof.yml"
    report = gate_jobs["report-and-package"]
    for artifact in ("phase2-native-pixel-proof", "phase2-symbol-specimens"):
        download = next(step for step in steps_using(report, "actions/download-artifact")
                        if step["with"].get("name") == artifact)
        assert download["with"]["path"] == f"/tmp/phase4/prior-phases/{artifact}"


@pytest.mark.parametrize("result", ["success", "failure", "skipped", "cancelled"])
def test_phase2_prerequisite_metadata_preserves_actual_outcome_for_the_report(tmp_path, result):
    job = workflow("native-release-gate.yml")["jobs"]["report-and-package"]
    step = next(s for s in job["steps"] if s.get("id") == "prerequisites")
    assert step["if"] == "always()"
    step = {**step, "run": step["run"].replace("/tmp/phase4", str(tmp_path))}
    executed = run_workflow_python(step, tmp_path, {
        "REVISION": REVISION, "PHASE2_RESULT": result, "PHASE2_REVISION": REVISION,
    })
    assert executed.returncode == 0, executed.stderr
    assert json.loads((tmp_path / "prior-phases/prerequisites.json").read_text()) == {
        "schema_version": 1, "revision": REVISION,
        "phase2": {"result": result, "revision": REVISION},
    }

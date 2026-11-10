"""Contracts for one comprehensive notation command and gated releases."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_container_provenance_uses_an_explicit_exact_workspace_trust_step():
    for filename in (path.name for path in (ROOT / ".github/workflows").glob("*.yml")):
        for job in workflow(filename)["jobs"].values():
            if "container" not in job:
                continue
            steps = job["steps"]
            checkout = next(i for i, step in enumerate(steps) if step.get("uses", "").startswith("actions/checkout@"))
            command = 'git config --global --add safe.directory "$GITHUB_WORKSPACE"'
            assert steps[checkout + 1].get("run") == command


def test_standalone_visual_cli_bootstraps_uninstalled_scripts_namespace(tmp_path):
    script = ROOT / "scripts/audit_phase3_whole_pieces.py"
    code = ("import runpy,sys; "
            f"sys.path.insert(0, {str(ROOT / 'scripts')!r}); "
            f"runpy.run_path({str(script)!r}); "
            "from scripts.notation_release_provenance import current_provenance; "
            "assert len(current_provenance()['revision']) == 40")
    result = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def workflow(name):
    path = ROOT / ".github/workflows" / name
    assert path.is_file(), f"missing workflow: {name}"
    # BaseLoader leaves GitHub's `on` key and expressions as strings.
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader)


def steps_using(job, action):
    return [step for step in job.get("steps", []) if step.get("uses", "").startswith(action + "@")]


# Workflow topology since 6a965d52 ("cap push gate at two minutes; move Godot and
# pixel regressions to manual suite"): native-notation.yml is the fast Python
# contract gate (scripts/ci-smoke.sh); the exhaustive notation command and the
# Godot regressions run only from explicit workflows.
def test_fast_contract_gate_runs_for_every_pr_and_main_push_and_is_reusable():
    ci = workflow("native-notation.yml")
    assert {"pull_request", "push", "workflow_call"} <= set(ci["on"])
    assert ci["on"]["push"]["branches"] == ["main"]
    for event in ("pull_request", "push"):
        filters = ci["on"][event] or {}
        assert not {"paths", "paths-ignore", "branches-ignore"} & set(filters)
    assert ci["on"]["pull_request"] in ("", {}, None)
    assert set(ci["jobs"]) == {"native-gate"}
    job = ci["jobs"]["native-gate"]
    assert "if" not in job and "strategy" not in job
    assert job.get("continue-on-error", "false") == "false"
    assert int(job["timeout-minutes"]) <= 2
    assert ci["permissions"] == {"contents": "read"}
    assert any(step.get("run") == "bash scripts/ci-smoke.sh" for step in job["steps"])


def test_one_explicit_notation_command_owns_exhaustive_coverage():
    invocations = []
    retired = (
        "check_user_midi_visual_regression.py", "check_user_midi_desktop.py",
        "check_native_notation.py", "audit_notation_proof.py",
        "audit_phase3_whole_pieces.py", "aggregate_phase3_corpus.py",
        "check_native_pixels.py", "check_native_symbols.py",
        "record_notation_mutations.py", "package_notation_evidence.py",
        "audit_native_release.py",
    )
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        data = workflow(path.name)
        assert not any(script in path.read_text() for script in retired), path
        for job in data["jobs"].values():
            for step in job.get("steps", []):
                if "scripts/check_native_verovio_overlay.py" in step.get("run", ""):
                    invocations.append((path.name, data, job, step))
    assert len(invocations) == 1, "one shared command owns exhaustive notation coverage"
    name, data, job, step = invocations[0]
    assert name == "native-complete-audit.yml"
    # Explicit only: never a pull_request or an unfiltered main push.
    assert "pull_request" not in data["on"] and "workflow_dispatch" in data["on"]
    assert data["on"]["push"]["paths"] == [".github/workflows/native-complete-audit.yml"]
    command = " ".join(step["run"].replace("\\\n", " ").split())
    assert "--only" not in command and "--headless" not in command
    assert "xvfb-run -a" in command and "1700x1000x24" in command
    assert "--shard-count 24" in command
    assert "if" not in step and "continue-on-error" not in step
    assert job["env"].get("LIBGL_ALWAYS_SOFTWARE") == "1"
    assert "PIANO_TEACHER_NATIVE_NOTATION" not in {**job.get("env", {}), **step.get("env", {})}


def test_complete_audit_installs_real_framebuffer_dependencies_and_preserves_failures():
    job = workflow("native-complete-audit.yml")["jobs"]["independent-source-shard"]
    assert int(job["timeout-minutes"]) >= 30
    assert job["strategy"]["fail-fast"] == "false"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    for dependency in ("xvfb", "xauth", "libgl1-mesa-dri", "Godot_v4.7.2-stable_linux"):
        assert dependency in commands
    assert "pip install -e '.[godot,test]'" in commands
    assert steps_using(job, "actions/checkout")[0]["with"]["ref"] == "${{ github.sha }}"
    uploads = steps_using(job, "actions/upload-artifact")
    assert len(uploads) == 1
    assert uploads[0]["if"] == "always()"
    assert not steps_using(job, "actions/download-artifact")


def test_release_reuses_the_regression_gate_and_only_exports_revision_after_success():
    regression = workflow("native-release-regressions.yml")
    release = workflow("native-release.yml")
    gate = release["jobs"]["exact-release-gate"]
    assert gate["uses"] == "./.github/workflows/native-release-regressions.yml"
    assert "with" not in gate, "both event and release check the current event SHA"
    job = regression["jobs"]["release-regression"]
    assert regression["on"]["workflow_call"]["outputs"]["revision"]["value"] == "${{ jobs.release-regression.outputs.revision }}"
    assert "pull_request" not in regression["on"] and "push" not in regression["on"]
    assert job["outputs"]["revision"] == "${{ steps.passed.outputs.revision }}"
    passed = next(step for step in job["steps"] if step.get("id") == "passed")
    regress = next(step for step in job["steps"] if "verify-notation.sh" in step.get("run", ""))
    assert job["steps"].index(passed) > job["steps"].index(regress)
    assert "if" not in passed and "continue-on-error" not in passed
    assert passed["env"]["REVISION"] == "${{ github.sha }}"
    downloads = steps_using(release["jobs"]["publish-draft"], "actions/download-artifact")
    assert [step["with"]["name"] for step in downloads] == ["native-release-candidate"]
    assert "--notes" in release["jobs"]["publish-draft"]["steps"][-1]["run"]


def test_local_reusable_workflow_calls_resolve_and_ci_smoke_is_the_push_gate():
    # phase0.yml and its network smoke scripts were retired (bcce6ab4, c5c06467);
    # the push gate is scripts/ci-smoke.sh, referenced by the fast workflow.
    assert "scripts/ci-smoke.sh" in workflow("native-notation.yml")["jobs"]["native-gate"]["steps"][-2]["run"]
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        for job in workflow(path.name)["jobs"].values():
            if job.get("uses", "").startswith("./.github/workflows/"):
                assert (ROOT / job["uses"]).is_file(), "dangling reusable workflow"


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

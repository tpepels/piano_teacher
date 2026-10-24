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


CANONICAL_COMMAND = ".venv/bin/python scripts/check_native_verovio_overlay.py --out /tmp/native-notation"


def test_native_notation_runs_for_every_pr_and_main_push_and_is_reusable():
    ci = workflow("native-notation.yml")
    assert {"pull_request", "push", "workflow_call"} <= set(ci["on"])
    assert ci["on"]["push"]["branches"] == ["main"]
    for event in ("pull_request", "push"):
        filters = ci["on"][event] or {}
        assert not {"paths", "paths-ignore", "branches-ignore"} & set(filters)
    assert ci["on"]["pull_request"] in ("", {}, None)
    assert set(ci["jobs"]) == {"native-notation"}
    job = ci["jobs"]["native-notation"]
    assert "if" not in job and "strategy" not in job
    assert job.get("continue-on-error", "false") == "false"
    assert ci["permissions"] == {"contents": "read"}


def test_one_unfiltered_notation_command_replaces_phase_and_scorestrip_gates():
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
                    invocations.append((job, step))
    assert len(invocations) == 1, "one shared command owns exhaustive notation coverage"
    job, step = invocations[0]
    command = " ".join(step["run"].replace("\\\n", " ").split())
    assert command.endswith(CANONICAL_COMMAND)
    assert "--only" not in command and "--headless" not in command
    assert "xvfb-run -a" in command
    assert '1600x1000x24' in command
    assert "if" not in step and "continue-on-error" not in step
    assert step.get("env", {}).get("LIBGL_ALWAYS_SOFTWARE") == "1"
    assert "PIANO_TEACHER_NATIVE_NOTATION" not in {**job.get("env", {}), **step.get("env", {})}
    assert "PIANO_TEACHER_NATIVE_NOTATION" not in workflow("native-notation.yml").get("env", {})


def test_native_notation_installs_real_framebuffer_dependencies_and_preserves_failures():
    job = workflow("native-notation.yml")["jobs"]["native-notation"]
    assert job["container"] == "archlinux:latest"
    assert int(job["timeout-minutes"]) >= 120
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    for dependency in ("godot", "xorg-server-xvfb", "xorg-xauth", "mesa", "cairo", "pango", "alsa-lib"):
        assert dependency in commands
    assert "pip install -e '.[godot,test]'" in commands
    assert steps_using(job, "actions/checkout")[0]["with"]["ref"] == "${{ github.sha }}"
    uploads = steps_using(job, "actions/upload-artifact")
    assert len(uploads) == 1
    assert uploads[0]["if"] == "always()"
    assert uploads[0]["with"]["path"] == "/tmp/native-notation/"
    assert not steps_using(job, "actions/download-artifact")


def test_release_reuses_canonical_gate_and_only_exports_revision_after_success():
    ci = workflow("native-notation.yml")
    release = workflow("native-release.yml")
    gate = release["jobs"]["exact-release-gate"]
    assert gate["uses"] == "./.github/workflows/native-notation.yml"
    assert "with" not in gate, "both event and release check the current event SHA"
    job = ci["jobs"]["native-notation"]
    assert ci["on"]["workflow_call"]["outputs"]["revision"]["value"] == "${{ jobs.native-notation.outputs.revision }}"
    assert job["outputs"]["revision"] == "${{ steps.passed.outputs.revision }}"
    passed = next(step for step in job["steps"] if step.get("id") == "passed")
    audit = next(step for step in job["steps"] if "check_native_verovio_overlay.py" in step.get("run", ""))
    assert job["steps"].index(passed) > job["steps"].index(audit)
    assert "if" not in passed and "continue-on-error" not in passed
    assert passed["env"]["REVISION"] == "${{ github.sha }}"
    downloads = steps_using(release["jobs"]["publish-draft"], "actions/download-artifact")
    assert [step["with"]["name"] for step in downloads] == ["native-release-candidate"]
    assert "--notes" in release["jobs"]["publish-draft"]["steps"][-1]["run"]


def test_general_app_integration_remains_separate_and_local_workflow_calls_resolve():
    integration = workflow("phase0.yml")
    commands = "\n".join(step.get("run", "") for job in integration["jobs"].values()
                         for step in job.get("steps", []))
    for command in ("-m pytest -q", "./scripts/check_godot.sh", "scripts/smoke_godot.py",
                    "scripts/smoke_adaptive_godot.py", "scripts/verify_library_pipeline.py",
                    "scripts/smoke_learning_ui.py", "scripts/review_art_direction.py"):
        assert command in commands
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

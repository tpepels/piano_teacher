"""End-to-end full-CI launcher regression with a tiny isolated git checkout."""
from __future__ import annotations

import getpass
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts.ci_full_shards import file_plan

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd, env=None):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, env=env, timeout=60)


@pytest.mark.skipif(shutil.which("git") is None, reason="Git required for revision-bound CI")
def test_four_parts_keep_all_failures_and_resume_on_the_same_revision(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "scripts/ci-full.sh").write_text((ROOT / "scripts/ci-full.sh").read_text())
    (repo / "scripts/ci_full_shards.py").write_text((ROOT / "scripts/ci_full_shards.py").read_text())
    (repo / "pyproject.toml").write_text('''[tool.pytest.ini_options]
testpaths=["tests"]
pythonpath=["."]
addopts="-m 'not slow'"
markers=["slow: slow tests"]
''')
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    for i in range(8):
        (repo / "tests" / f"test_case_{i}.py").write_text(
            "def test_case_3(:\n" if i == 3 else
            f"def test_case_{i}():\n    assert True\n")
    assert run("git", "init", "-q", cwd=repo).returncode == 0
    assert run("git", "config", "user.email", "ci@example.invalid", cwd=repo).returncode == 0
    assert run("git", "config", "user.name", "CI", cwd=repo).returncode == 0
    assert run("git", "add", ".", cwd=repo).returncode == 0
    assert run("git", "commit", "-qm", "initial", cwd=repo).returncode == 0
    out = tmp_path / "results"
    base = tmp_path / "tmp"
    base.mkdir()
    legacy = base / ("pytest-of-" + getpass.getuser()) / "pytest-99"
    legacy.mkdir(parents=True)
    (legacy / "artifact").write_text("old")
    env = dict(os.environ, PYTHON=sys.executable, TMPDIR=str(base),
               CI_FULL_RESULTS_DIR=str(out))
    launcher = ["bash", "scripts/ci-full.sh"]
    broken_shard = file_plan(str(repo))[0]["tests/test_case_3.py"]
    first = run(*launcher, "--all", cwd=repo, env=env)
    assert first.returncode != 0, first.stdout + first.stderr
    assert "CI_FULL_HALTED:" in first.stdout
    assert first.stdout.count("CI_FULL_PART_START:") == broken_shard
    # An enclosing pytest process normally prevents legacy cleanup. If the
    # runner cannot see that parent, it may instead reclaim the old tree.
    if "CI_FULL_TEMP_CLEANUP_SKIPPED:" in first.stdout:
        assert legacy.exists(), "active pytest must prevent legacy cleanup"
    else:
        assert "CI_FULL_TEMP_CLEANUP: removed 1" in first.stdout
        assert not legacy.exists(), "old pytest tree must be reclaimed"
    revision = run("git", "rev-parse", "--short=12", "HEAD", cwd=repo).stdout.strip()
    for i in range(1, 5):
        status = out / revision / f"shard-{i}.status"
        log = out / revision / f"shard-{i}.log"
        if i < broken_shard:
            assert status.read_text().strip() == "PASS"
            assert log.is_file()
        elif i == broken_shard:
            assert status.read_text().strip() == "FAIL"
            assert log.is_file()
        else:
            assert not status.exists() and not log.exists(), "green-only chaining must halt"
    assert not list(base.glob("piano-teacher-ci-full-*")), "shard tmp must be deleted"

    again = run(*launcher, "--all", cwd=repo, env=env)
    assert again.returncode != 0
    assert again.stdout.count("CI_FULL_PART_SKIP:") == broken_shard - 1
    assert again.stdout.count("CI_FULL_PART_START:") == 1
    assert "CI_FULL_HALTED:" in again.stdout

    # On a new Git commit, previous PASS records cannot be reused.
    (repo / "tests/test_case_3.py").write_text("def test_case_3():\n    assert True\n")
    assert run("git", "add", ".", cwd=repo).returncode == 0
    assert run("git", "commit", "-qm", "fixed", cwd=repo).returncode == 0
    status = run(*launcher, "--status", cwd=repo, env=env)
    assert status.returncode != 0 and "INCOMPLETE (0/4" in status.stdout

    # Explicit --shard 3 runs shard 3 and then 4 automatically, not 1 or 2.
    partial = run(*launcher, "--shard", "3", cwd=repo, env=env)
    assert partial.returncode == 0, partial.stdout + partial.stderr
    assert partial.stdout.count("CI_FULL_PART_START:") == 2
    assert "CI_FULL_SEQUENCE_DONE: parts 3-4 passed" in partial.stdout
    new_revision = run("git", "rev-parse", "--short=12", "HEAD", cwd=repo).stdout.strip()
    for i in (3, 4):
        assert (out / new_revision / f"shard-{i}.status").read_text().strip() == "PASS"
    for i in (1, 2):
        assert not (out / new_revision / f"shard-{i}.status").exists()

    # Starting at one now advances to two, then skips already-green 3 and 4.
    fixed = run(*launcher, "--shard", "1", cwd=repo, env=env)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    assert fixed.stdout.count("CI_FULL_PART_START:") == 2
    assert fixed.stdout.count("CI_FULL_PART_SKIP:") == 2
    assert "CI_FULL_COMPLETE: PASS (4/4" in fixed.stdout

    # A complete gate is then a cheap status-only run on the same revision.
    skip = run(*launcher, "--all", cwd=repo, env=env)
    assert skip.returncode == 0, skip.stdout + skip.stderr
    assert skip.stdout.count("CI_FULL_PART_SKIP:") == 4
    assert skip.stdout.count("CI_FULL_PART_START:") == 0

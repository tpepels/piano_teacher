"""End-to-end full-CI launcher regression with a tiny isolated git checkout."""
from __future__ import annotations

import getpass
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

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
            f"def test_case_{i}():\n    assert {i} != 3\n")
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
    first = run(*launcher, "--all", cwd=repo, env=env)
    assert first.returncode != 0, first.stdout + first.stderr
    # An enclosing pytest process normally prevents legacy cleanup. If the
    # runner cannot see that parent, it may instead reclaim the old tree.
    if "CI_FULL_TEMP_CLEANUP_SKIPPED:" in first.stdout:
        assert legacy.exists(), "active pytest must prevent legacy cleanup"
    else:
        assert "CI_FULL_TEMP_CLEANUP: removed 1" in first.stdout
        assert not legacy.exists(), "old pytest tree must be reclaimed"
    revision = run("git", "rev-parse", "--short=12", "HEAD", cwd=repo).stdout.strip()
    states = {i: (out / revision / f"shard-{i}.status").read_text().strip()
              for i in range(1, 5)}
    assert sorted(states.values()) == ["FAIL", "PASS", "PASS", "PASS"]
    assert all((out / revision / f"shard-{i}.log").is_file() for i in range(1, 5))
    assert not list(base.glob("piano-teacher-ci-full-*")), "shard tmp must be deleted"

    again = run(*launcher, "--all", cwd=repo, env=env)
    assert again.returncode != 0
    assert again.stdout.count("CI_FULL_PART_SKIP:") == 3
    assert again.stdout.count("CI_FULL_PART_START:") == 1
    # On another commit, prior PASS files cannot be silently reused.
    (repo / "tests/test_case_3.py").write_text("def test_case_3():\n    assert True\n")
    assert run("git", "add", ".", cwd=repo).returncode == 0
    assert run("git", "commit", "-qm", "fixed", cwd=repo).returncode == 0
    status = run(*launcher, "--status", cwd=repo, env=env)
    assert status.returncode != 0 and "INCOMPLETE (0/4" in status.stdout
    fixed = run(*launcher, "--all", cwd=repo, env=env)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    assert "CI_FULL_COMPLETE: PASS (4/4" in fixed.stdout

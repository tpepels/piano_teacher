"""The quarantine hook: strict xfail, stale-line detection, file-level entries."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import quarantine_plugin

ROOT = Path(__file__).resolve().parents[1]

SUITE = {
    "test_sample.py": "def test_passes():\n    pass\n\ndef test_fails():\n    assert False\n",
    "test_other.py": "def test_a():\n    pass\n\ndef test_b():\n    assert False\n",
}


def run(tmp_path, quarantine: str, *args: str):
    for name, body in SUITE.items():
        (tmp_path / name).write_text(body)
    (tmp_path / "conftest.py").write_text(
        f"import sys\nsys.path.insert(0, {str(ROOT / 'tests')!r})\n"
        "from quarantine_plugin import pytest_collection_modifyitems  # noqa\n")
    (tmp_path / "q.txt").write_text(quarantine)
    env = {**os.environ, "PIANO_QUARANTINE_FILE": str(tmp_path / "q.txt")}
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
                          cwd=tmp_path, env=env, capture_output=True, text=True, check=False)


def test_quarantined_failing_test_is_xfail(tmp_path):
    r = run(tmp_path, "test_sample.py::test_fails | environment: demo\ntest_other.py::test_b | demo\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "2 xfailed" in r.stdout


def test_quarantined_passing_test_fails_loudly(tmp_path):
    r = run(tmp_path, "test_sample.py::test_passes | demo\ntest_sample.py::test_fails | demo\n")
    assert r.returncode != 0
    assert "XPASS(strict)" in r.stdout and "quarantined: demo" in r.stdout


def test_file_level_entry_covers_every_test_in_file(tmp_path):
    r = run(tmp_path, "test_other.py | whole file\n", "test_other.py")
    assert "XPASS(strict)" in r.stdout  # test_a passes inside a quarantined file
    assert "1 xfailed" in r.stdout


def test_unknown_id_is_reported(tmp_path):
    r = run(tmp_path, "test_sample.py::test_gone | stale\n")
    assert r.returncode != 0
    assert "stale quarantine entries" in r.stderr + r.stdout and "test_gone" in r.stderr + r.stdout


def test_missing_file_is_reported(tmp_path):
    r = run(tmp_path, "test_nowhere.py | stale\n")
    assert r.returncode != 0 and "file does not exist" in r.stderr + r.stdout


def test_selecting_one_test_id_does_not_make_other_entries_stale(tmp_path):
    r = run(tmp_path, "test_other.py::test_b | demo\n", "test_other.py::test_a")
    assert r.returncode == 0, r.stdout + r.stderr


def test_flaky_reason_is_non_strict(tmp_path):
    r = run(tmp_path, "test_sample.py::test_passes | flaky: timing\ntest_sample.py::test_fails | flaky: timing\n", "test_sample.py")
    assert r.returncode == 0, r.stdout + r.stderr


def test_partial_run_does_not_flag_entries_of_uncollected_files(tmp_path):
    r = run(tmp_path, "test_other.py::test_b | demo\n", "test_sample.py::test_passes")
    assert r.returncode == 0, r.stdout + r.stderr


def test_parse_rejects_missing_reason_and_duplicates():
    with pytest.raises(pytest.UsageError):
        quarantine_plugin.parse("tests/a.py::t\n")
    with pytest.raises(pytest.UsageError):
        quarantine_plugin.parse("a | x\na | y\n")
    assert quarantine_plugin.parse("# c\n\na::b | why | more\n") == {"a::b": "why | more"}


def test_repo_quarantine_file_has_no_stale_entries():
    # Guards the committed file even for runs that never collect its tests.
    for target in quarantine_plugin.parse((ROOT / "tests" / "quarantine.txt").read_text()):
        assert (ROOT / target.split("::", 1)[0]).is_file(), target

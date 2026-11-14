"""Shard-local pytest temporary artifacts must not exhaust /tmp mid-shard.

Pytest normally retains every function's tmp_path until the entire run
exits. Our large genuine ZIP/framebuffer cases can then exceed a developer's
user quota even though each case individually fits. Keep failed evidence,
but remove each successful test's directory before the next test begins.
"""
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_ci_shard_reclaims_passing_temps_and_keeps_failure_evidence(tmp_path):
    runner = (ROOT / "scripts/ci-full.sh").read_text()
    assert "-o tmp_path_retention_policy=failed" in runner

    suite = tmp_path / "cases"
    suite.mkdir()
    (suite / "test_retention.py").write_text(
        "from pathlib import Path\n"
        "def test_a_written_evidence(tmp_path, tmp_path_factory):\n"
        "    (tmp_path / 'archive.bin').write_bytes(b'x' * 32768)\n"
        "    (tmp_path_factory.getbasetemp() / 'first_path').write_text(str(tmp_path))\n"
        "def test_b_next_case_checks_prior_cleanup(tmp_path, tmp_path_factory):\n"
        "    first = Path((tmp_path_factory.getbasetemp() / 'first_path').read_text())\n"
        "    assert not first.exists(), 'passed case retained its expensive artifact'\n"
        "    (tmp_path / 'failure-evidence.txt').write_text('preserved')\n"
        "    assert False, 'deliberate failure keeps raw evidence'\n"
    )
    base = tmp_path / "pytest"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o",
         "tmp_path_retention_policy=failed", "--basetemp", str(base),
         str(suite / "test_retention.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=30)
    # The ONLY failure must be the deliberate second case; the first
    # artifact had already been reclaimed before the next case ran.
    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 failed, 1 passed" in result.stdout, result.stdout + result.stderr
    assert not list(base.glob("test_a_written_evidence*/archive.bin"))
    assert list(base.glob("test_b_next_case_checks_pr*/failure-evidence.txt"))

"""The shell runner's embedded Python is part of the executable CI surface.

A single unescaped apostrophe in its cleanup preflight previously prevented
every shard from starting. Parse BOTH interpreters in the fast smoke gate.
"""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/ci-full.sh"


def test_full_ci_runner_is_valid_bash():
    result = subprocess.run(["bash", "-n", str(RUNNER)],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_full_ci_embedded_python_preflight_compiles():
    source = RUNNER.read_text()
    marker = "<<'PY'\n"
    assert source.count(marker) == 1
    preflight = source.split(marker, 1)[1].split("\nPY\n", 1)[0]
    assert preflight.strip()
    compile(ast.parse(preflight, filename="scripts/ci-full.sh:preflight"),
            "scripts/ci-full.sh:preflight", "exec")


def test_auto_advance_only_after_success_and_never_drop_failed_status():
    source = RUNNER.read_text()
    assert "for ((number=start; number<=SHARDS; number++)); do" in source
    assert 'if ! run_part "$number"; then' in source
    assert "CI_FULL_HALTED:" in source
    assert 'status_summary || :' in source
    assert "CI_FULL_SEQUENCE_DONE:" in source
    assert 'if [[ "$mode" == shard && ${#pytest_args[@]} -gt 0 ]]; then' in source


def test_fail_fast_stops_at_one_error_but_keeps_release_pass_semantics():
    source = RUNNER.read_text()
    assert '--fail-fast) fail_fast=1; shift ;;' in source
    assert 'if [[ "$fail_fast" -eq 1 ]]; then fail_fast_args=(-x); fi' in source
    assert '"${fail_fast_args[@]}" tests "${pytest_args[@]}"' in source
    # Fail-fast is orthogonal to diagnostic pytest args. A successful run
    # of all selected cases must still record a clean full-shard PASS.
    assert 'if [[ "$clean" -eq 1 && ${#pytest_args[@]} -eq 0 ]]; then' in source
    assert "printf 'PASS\\n' >" in source

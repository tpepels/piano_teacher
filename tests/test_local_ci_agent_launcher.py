"""Local CI agent launcher: Claude Code invocation, logs, restart and stops.

Runs the real ``scripts/local-ci-agent.sh`` in a tiny isolated git checkout
with a stub ``claude`` executable, so no model or full suite is started.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("flock") is None,
    reason="git and flock are required by the launcher")

SCOPE_STUB = """import pathlib, sys
sys.exit(0 if pathlib.Path('tests/ci-scope.json').is_file() else 1)
"""

# The stub records its arguments, then acts according to STUB_MODE.
CLAUDE_STUB = r"""#!/usr/bin/env bash
printf '%s\n' "$@" > "$STUB_DIR/args.$(date +%s%N)"
echo '{"type":"system","subtype":"init"}'
case "$STUB_MODE" in
  audit)
    mkdir -p tests docs/verification
    echo '{"schema":1,"modules":{}}' > tests/ci-scope.json
    printf 'audit\n\nScope audit: COMPLETE\n' > docs/verification/ci-current-scope-audit.md
    git add -A >/dev/null && git commit -qm audit
    echo '{"type":"result","subtype":"success","is_error":false,"result":"root cause: none; audit committed"}' ;;
  idle)
    echo '{"type":"result","subtype":"success","is_error":false,"result":"nothing committed"}' ;;
  error)
    echo '{"type":"result","subtype":"error_during_execution","is_error":true,"result":"usage limit"}' ;;
  dirty)
    echo stray > stray.txt
    echo '{"type":"result","subtype":"success","is_error":false,"result":"left a file"}' ;;
esac
"""


def run(*args, cwd, env=None):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, env=env, timeout=60)


@pytest.fixture
def checkout(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts/local-ci-agent.sh", repo / "scripts/local-ci-agent.sh")
    (repo / "scripts/ci-scope.py").write_text(SCOPE_STUB)
    (repo / "scripts/ci-full.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    (repo / "AGENTS.md").write_text("stub\n")
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    claude = stub_dir / "claude"
    claude.write_text(CLAUDE_STUB)
    claude.chmod(0o755)
    for command in (("init", "-q", "-b", "main"), ("config", "user.email", "ci@example.invalid"),
                    ("config", "user.name", "CI"), ("add", "."), ("commit", "-qm", "initial")):
        assert run("git", *command, cwd=repo).returncode == 0
    env = dict(os.environ, PYTHON=sys.executable, CLAUDE_BIN=str(claude), CI_AGENT_CLI="claude",
               GODOT_BIN="true", STUB_DIR=str(stub_dir), CI_AGENT_LOG_DIR=str(tmp_path / "logs"))
    env.pop("CI_AGENT_CLAUDE_ARGS", None)
    env.pop("CI_AGENT_CLAUDE_PERMISSION_MODE", None)
    env.pop("CI_AGENT_MAX_ROUNDS", None)
    return repo, env, stub_dir, tmp_path / "logs"


def launch(repo, env, mode, *args):
    return run("bash", "scripts/local-ci-agent.sh", *args, cwd=repo, env=dict(env, STUB_MODE=mode))


def calls(stub_dir):
    return [path.read_text().splitlines() for path in sorted(stub_dir.glob("args.*"))]


def test_claude_turn_is_noninteractive_logged_and_resumes_after_its_commit(checkout):
    repo, env, stub_dir, logs = checkout
    done = launch(repo, env, "audit", "--audit-only")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "CI_AGENT_TURN_START: 1" in done.stdout and "agent=claude" in done.stdout
    assert "CI_AGENT_TURN_COMMITTED: 1" in done.stdout
    assert "CI_AGENT_PHASE_A_COMPLETE:" in done.stdout
    (args,) = calls(stub_dir)
    assert args[0] == "-p" and "PHASE A ONLY" in args[1]
    assert args[args.index("--permission-mode") + 1] == "auto"
    assert args[args.index("--output-format") + 1] == "stream-json" and "--verbose" in args
    assert "--dangerously-skip-permissions" not in args
    assert "ci-repair-log.md" in args[1]
    events = [json.loads(line) for line in (logs / "turn-1.claude.log").read_text().splitlines()]
    assert events[-1]["type"] == "result"
    assert (logs / "turn-1.summary.txt").read_text().strip() == "root cause: none; audit committed"
    assert (logs / "turn-1.prompt.txt").read_text().strip() == args[1]
    assert (logs / "round-counter").read_text().strip() == "2"

    # A restart keeps monotonic log numbers and needs no further agent turn.
    again = launch(repo, env, "audit", "--audit-only")
    assert again.returncode == 0, again.stdout + again.stderr
    assert len(calls(stub_dir)) == 1
    assert (logs / "round-counter").read_text().strip() == "3"
    assert (logs / "turn-1.summary.txt").is_file()


def test_turn_without_commit_gets_one_blocker_investigation_then_stops(checkout):
    repo, env, stub_dir, logs = checkout
    stopped = launch(repo, env, "idle", "--audit-only")
    assert stopped.returncode == 3, stopped.stdout + stopped.stderr
    assert "CI_AGENT_NO_PROGRESS: turn 1" in stopped.stdout
    assert "no committed progress in two consecutive turns" in stopped.stderr
    first, second = calls(stub_dir)
    assert "ENDED WITHOUT A COMMIT" not in first[1]
    assert "ENDED WITHOUT A COMMIT" in second[1] and "turn-1.summary.txt" in second[1]
    assert (logs / "turn-2.summary.txt").read_text().strip() == "nothing committed"


def test_failed_agent_result_and_dirty_checkout_stop_the_launcher(checkout):
    repo, env, stub_dir, logs = checkout
    failed = launch(repo, env, "error", "--audit-only")
    assert failed.returncode == 70, failed.stdout + failed.stderr
    assert "CI_AGENT_STOP: claude turn 1 failed" in failed.stderr
    assert (logs / "turn-1.summary.txt").read_text().strip() == "usage limit"
    assert len(calls(stub_dir)) == 1

    dirty = launch(repo, env, "dirty", "--audit-only")
    assert dirty.returncode == 2, dirty.stdout + dirty.stderr
    assert "checkout is dirty" in dirty.stderr and "stray.txt" in dirty.stderr
    refused = launch(repo, env, "audit", "--audit-only")
    assert refused.returncode == 2 and len(calls(stub_dir)) == 2, "dirty tree blocks a new turn"


def test_permission_mode_and_extra_arguments_are_operator_controlled(checkout):
    repo, env, stub_dir, _ = checkout
    env = dict(env, CI_AGENT_CLAUDE_PERMISSION_MODE="acceptEdits", CI_AGENT_CLAUDE_ARGS="--model opus")
    assert launch(repo, env, "audit", "--audit-only").returncode == 0
    (args,) = calls(stub_dir)
    assert args[args.index("--permission-mode") + 1] == "acceptEdits"
    assert args[args.index("--model") + 1] == "opus"
    invalid = launch(repo, dict(env, CI_AGENT_CLI="other"), "audit", "--audit-only")
    assert invalid.returncode == 2 and "must be claude or codex" in invalid.stderr

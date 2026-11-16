#!/usr/bin/env bash
# Persistent local agent handoff: audit current tests first, then repair CI.
# Runs ON the developer's machine so Godot, real fixtures and local pytest
# artifacts are available. One non-interactive agent turn (Claude Code by
# default, Codex optionally) per scope/failure iteration.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

usage() {
    cat <<'HELP'
Usage: bash scripts/local-ci-agent.sh [--audit-only]

Requires a logged-in Claude Code CLI (or Codex CLI), Godot 4.7 and the
project .venv.
Works on main only. Starts with a complete current-test scope audit,
then runs the four-part full CI on a clean commit, stopping on its first
failing test for one repair at a time. Final gates also run smoke, Godot syntax, focused+corpus hybrid
verification and require an empty quarantine. On each actual code change
the full suite is tested again on the new revision.

Log/status directory: playtest-results/local-ci-agent/
Durable hand-over record: docs/verification/ci-repair-log.md (committed).
Optional environment:
  CI_AGENT_CLI=claude|codex     agent CLI (default: claude when installed)
  CLAUDE_BIN / CODEX_BIN        executable override
  CI_AGENT_CLAUDE_PERMISSION_MODE  Claude permission mode (default: auto)
  CI_AGENT_CLAUDE_ARGS          extra Claude CLI arguments (e.g. --model ...)
  CI_AGENT_MAX_ROUNDS=N         cap attempts (unlimited by default)
Ctrl-C stops the launcher.
A turn without a commit gets ONE blocker-investigation turn; a second
consecutive turn without a commit, an environment failure or a dirty working
tree stops nonzero.
Does not force-push, switch branches, create worktrees, or auto-stage files.
HELP
}

audit_only=0
while (($#)); do
    case "$1" in
        --audit-only) audit_only=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

PYTHON="${PYTHON:-$PWD/.venv/bin/python}"
CODEX="${CODEX_BIN:-codex}"
CLAUDE="${CLAUDE_BIN:-claude}"
AGENT_CLI="${CI_AGENT_CLI:-}"
if [[ -z "$AGENT_CLI" ]]; then
    if command -v "$CLAUDE" >/dev/null 2>&1; then AGENT_CLI=claude; else AGENT_CLI=codex; fi
fi
case "$AGENT_CLI" in
    claude) AGENT_BIN="$CLAUDE" ;;
    codex) AGENT_BIN="$CODEX" ;;
    *) echo "CI_AGENT_ERROR: CI_AGENT_CLI must be claude or codex" >&2; exit 2 ;;
esac
MAX_ROUNDS="${CI_AGENT_MAX_ROUNDS:-0}"
OUT="${CI_AGENT_LOG_DIR:-$PWD/playtest-results/local-ci-agent}"
[[ "$MAX_ROUNDS" =~ ^(0|[1-9][0-9]*)$ ]] || {
    echo "CI_AGENT_ERROR: CI_AGENT_MAX_ROUNDS must be 0 (unlimited) or positive" >&2; exit 2;
}
[[ -x "$PYTHON" ]] || { echo "CI_AGENT_ERROR: .venv Python missing at $PYTHON" >&2; exit 2; }
command -v "$AGENT_BIN" >/dev/null 2>&1 || {
    echo "CI_AGENT_ERROR: $AGENT_CLI CLI missing ($AGENT_BIN); install it and log in first" >&2; exit 2;
}
if [[ -z "${GODOT_BIN:-}" ]] && ! command -v godot >/dev/null 2>&1 && \
        ! command -v godot4 >/dev/null 2>&1; then
    echo "CI_AGENT_ERROR: Godot executable missing; framebuffer CI needs Godot" >&2
    exit 2
fi
[[ -f AGENTS.md && -f scripts/ci-scope.py && -f scripts/ci-full.sh ]] || {
    echo "CI_AGENT_ERROR: incomplete local CI handoff; git pull --ff-only first" >&2; exit 2;
}
mkdir -p "$OUT"
command -v flock >/dev/null 2>&1 || {
    echo "CI_AGENT_ERROR: flock required to prevent concurrent repair agents" >&2; exit 2;
}
exec 9>"$OUT/launcher.lock"
flock -n 9 || { echo "CI_AGENT_ERROR: another local CI agent owns the lock" >&2; exit 2; }

ensure_main_clean() {
    [[ "$(git branch --show-current)" == main ]] || {
        echo "CI_AGENT_STOP: not on the main branch" >&2; exit 2;
    }
    if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
        echo "CI_AGENT_STOP: checkout is dirty; preserve and inspect changes" >&2
        git status --short >&2
        exit 2
    fi
}
ensure_main_clean
"$PYTHON" -m pytest --version >/dev/null
CODEX_POLICY=(--sandbox workspace-write)
CLAUDE_POLICY=()
if [[ "$AGENT_CLI" == codex ]]; then
    if "$CODEX" exec --help 2>&1 | grep -q -- '--approve-for-me'; then
        # Recent CLI releases can automatically review workspace-write
        # approvals, including Git operations, without an interactive dialog.
        CODEX_POLICY=(--approve-for-me)
    fi
else
    # Claude Code print mode never opens a dialog. "auto" reviews each tool
    # call automatically instead of bypassing permission checks.
    CLAUDE_POLICY=(--permission-mode "${CI_AGENT_CLAUDE_PERMISSION_MODE:-auto}")
    if [[ -n "${CI_AGENT_CLAUDE_ARGS:-}" ]]; then
        # Intentional word splitting of an operator-supplied argument list.
        # shellcheck disable=SC2206
        CLAUDE_POLICY+=(${CI_AGENT_CLAUDE_ARGS})
    fi
fi

# Final assistant message of a Claude stream-json transcript. Exit 1 when the
# transcript holds no successful result event (API error, refusal, limits).
claude_summary() {
    "$PYTHON" - "$1" "$2" <<'PY'
import json
import sys

result = None
with open(sys.argv[1], encoding="utf-8", errors="replace") as stream:
    for line in stream:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            result = event
if result is None:
    sys.exit(1)
with open(sys.argv[2], "w", encoding="utf-8") as out:
    out.write(str(result.get("result") or "") + "\n")
sys.exit(1 if result.get("is_error") else 0)
PY
}

# Each turn is an independent agent invocation. Git commits, the checked-in
# scope registry and docs/verification/ci-repair-log.md preserve progress
# across context windows or CLI restarts. The launcher runs full CI itself.
no_progress=0
run_agent() {
    local turn="$1" task="$2" before="$3" code=0
    local prompt_file="$OUT/turn-$turn.prompt.txt"
    local log_file="$OUT/turn-$turn.$AGENT_CLI.log"
    local summary_file="$OUT/turn-$turn.summary.txt"
    if ((no_progress > 0)); then
        task="THE PREVIOUS TURN ($((turn - 1))) ENDED WITHOUT A COMMIT. Read its summary $OUT/turn-$((turn - 1)).summary.txt and log first, identify the concrete blocker, and do not repeat the same attempt. Either commit real progress, or record the blocker precisely in docs/verification/ci-repair-log.md and commit that record so a human can act. $task"
    fi
    printf '%s\n' "$task" > "$prompt_file"
    echo "CI_AGENT_TURN_START: $turn revision=$before agent=$AGENT_CLI"
    if [[ "$AGENT_CLI" == codex ]]; then
        # Codex CLI: automatic approval review with a workspace-write
        # sandbox, not unsandboxed arbitrary execution.
        if "$CODEX" exec "${CODEX_POLICY[@]}" -C "$PWD" \
                --output-last-message "$summary_file" "$task" \
                2>&1 | tee "$log_file"; then
            code=0
        else
            code=${PIPESTATUS[0]}
        fi
    else
        # Claude Code: one print-mode session in this checkout. The complete
        # event transcript is the turn log; stdin is closed so the CLI can
        # never wait for interactive input.
        if "$CLAUDE" -p "$task" "${CLAUDE_POLICY[@]}" \
                --output-format stream-json --verbose \
                < /dev/null > "$log_file" 2> "$log_file.stderr"; then
            code=0
        else
            code=$?
        fi
        if ! claude_summary "$log_file" "$summary_file" && [[ "$code" -eq 0 ]]; then
            code=70
        fi
        [[ -s "$summary_file" ]] && cat "$summary_file"
    fi
    if [[ "$code" -ne 0 ]]; then
        echo "CI_AGENT_STOP: $AGENT_CLI turn $turn failed ($code); $log_file" >&2
        exit "$code"
    fi
    ensure_main_clean
    if [[ "$(git rev-parse HEAD)" == "$before" ]]; then
        no_progress=$((no_progress + 1))
        if ((no_progress >= 2)); then
            echo "CI_AGENT_STOP: no committed progress in two consecutive turns (last: $turn); $log_file" >&2
            exit 3
        fi
        echo "CI_AGENT_NO_PROGRESS: turn $turn made no commit; next turn investigates the blocker"
        return 0
    fi
    no_progress=0
    echo "CI_AGENT_TURN_COMMITTED: $turn $(git rev-parse --short=12 HEAD)"
}

scope_complete() {
    "$PYTHON" scripts/ci-scope.py --check >/dev/null 2>&1 &&
        [[ -s docs/verification/ci-current-scope-audit.md ]] &&
        grep -qx 'Scope audit: COMPLETE' docs/verification/ci-current-scope-audit.md
}

# Each gate writes its full log. The first nonzero gate becomes the sole next
# defect: do not hide failures by continuing to unrelated checks.
gate() {
    local tag="$1"
    shift
    local log="$OUT/round-$round.$tag.log"
    echo "CI_AGENT_GATE_START: $tag revision=$(git rev-parse --short=12 HEAD)"
    if "$@" 2>&1 | tee "$log"; then
        echo "CI_AGENT_GATE_PASS: $tag"
        return 0
    fi
    echo "CI_AGENT_GATE_FAIL: $tag log=$log"
    failure_gate="$tag"
    failure_log="$log"
    return 1
}

# Preserve monotonic log IDs across process restarts. Restarting the runner
# does not discard previous agent summaries or independent shard evidence.
counter="$OUT/round-counter"
round=0
if [[ -f "$counter" ]]; then
    round="$(cat "$counter")"
    [[ "$round" =~ ^[0-9]+$ ]] || {
        echo "CI_AGENT_ERROR: invalid $counter" >&2; exit 2;
    }
fi
attempts=0
while ((MAX_ROUNDS == 0 || attempts < MAX_ROUNDS)); do
    attempts=$((attempts + 1))
    round=$((round + 1))
    printf '%s\n' "$round" > "$counter"
    ensure_main_clean
    before="$(git rev-parse HEAD)"

    if ! scope_complete; then
        echo "CI_AGENT_PHASE_A: current-test scope audit, round $round"
        task="You are the local repository agent for tpepels/piano_teacher. Read AGENTS.md and ROADMAP.md. PHASE A ONLY: inventory ALL pytest test files, 144+ Godot scripts and all .github workflow definitions using python scripts/ci-scope.py --inventory and the four-shard plan. Review each test case, native harness and workflow job against the actual current Godot + embedded Python application. Delete/rewrite only demonstrably obsolete cases, retain or fix current failures, revise smoke and quarantine references as warranted. Produce tests/ci-scope.json with schema=1, entries keyed by every remaining pytest module, Godot test script and CI workflow, each containing an existing current source path as owner and a concrete contract string. Produce docs/verification/ci-current-scope-audit.md documenting pytest, native-script and workflow review, including individual cases inside mixed modules and every removed case with reason/replacement; its own final line must be exactly Scope audit: COMPLETE only after the review is genuinely complete. Pass python scripts/ci-scope.py --check, bash scripts/ci-full.sh --plan and collection checks. Commit coherent progress directly on main, no worktrees. DO NOT start full four-shard CI and DO NOT pretend the audit is complete when unfinished. When unable to finish in one turn, commit the partial audit evidence and continue on the next agent turn. Current revision: $before. Read docs/verification/ci-repair-log.md first if it exists and append this turn (work done, commits, remaining modules) to it before committing. See $OUT for prior turn logs."
        run_agent "$round" "$task" "$before"
        continue
    fi

    if [[ "$audit_only" -eq 1 ]]; then
        echo "CI_AGENT_PHASE_A_COMPLETE: reviewed current test/CI scope on $before"
        exit 0
    fi

    echo "CI_AGENT_PHASE_B: fix first remaining current-CI failure, round $round"
    failure_gate=''
    failure_log=''
    # ci-full.sh runs four deterministic disjoint shards sequentially. -x
    # stops at the FIRST failed test, while a passing shard still runs every
    # selected case and records PASS only on the same clean revision.
    if ! gate full bash scripts/ci-full.sh --all --fail-fast; then
        :
    elif ! gate no-quarantine "$PYTHON" scripts/ci-scope.py --check-unquarantined; then
        :
    elif ! gate smoke bash scripts/ci-smoke.sh; then
        :
    elif ! gate godot-syntax bash scripts/check-godot-syntax.sh; then
        :
    elif ! gate hybrid-focused bash scripts/verify-hybrid-workflow.sh --focused; then
        :
    elif ! gate hybrid-corpus bash scripts/verify-hybrid-workflow.sh --corpus; then
        :
    else
        # All gates were run on this SAME revision with a clean tree. No
        # selected quarantine test can be hiding an unresolved failure.
        ensure_main_clean
        [[ "$(git rev-parse HEAD)" == "$before" ]] || {
            echo "CI_AGENT_STOP: revision changed during final verification" >&2
            exit 3
        }
        bash scripts/ci-full.sh --status | tee "$OUT/final-status.log"
        printf '%s\n' "$before" > "$OUT/PASSED_COMMIT"
        echo "CI_AGENT_COMPLETE: scope audit + all CI gates PASS on $before"
        exit 0
    fi
    task="You are the local repository agent for tpepels/piano_teacher. Read AGENTS.md and ROADMAP.md. PHASE B ONLY: fix the FIRST failing CURRENT application test or gate from the local log at $failure_log (gate $failure_gate), at clean main revision $before. Read the full traceback/artifacts and current implementation, establish root cause, make the smallest complete production/test correction without weakening checks or inventing legacy behavior, and run focused tests as possible. Maintain the current test-scope registry if files are added or removed. Commit the fix directly on main, no worktrees. Leave the checkout clean and return control to the launcher; it will repeat all four CI shards at the new commit. If the failure is environment-only, report the real blocker instead of claiming success. Read docs/verification/ci-repair-log.md first and append this turn (failure, root cause, files, tests run, commit, remaining failures) to it in the same commit. Previous agent logs: $OUT."
    run_agent "$round" "$task" "$before"
done

echo "CI_AGENT_STOP: exhausted CI_AGENT_MAX_ROUNDS=$MAX_ROUNDS; logs in $OUT" >&2
exit 4

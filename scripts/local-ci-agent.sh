#!/usr/bin/env bash
# Persistent local Codex handoff: audit current tests first, then repair CI.
# Runs ON the developer's machine so Godot, real fixtures and local pytest
# artifacts are available. One Codex turn per scope/failure iteration.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

usage() {
    cat <<'HELP'
Usage: bash scripts/local-ci-agent.sh [--audit-only]

Requires a logged-in Codex CLI, Godot 4.7 and the project .venv.
Works on main only. Starts with a complete current-test scope audit,
then runs the four-part full CI on a clean commit, fixing one failure at a
time. Final gates also run smoke, Godot syntax, focused+corpus hybrid
verification and require an empty quarantine. On each actual code change
the full suite is tested again on the new revision.

Log/status directory: playtest-results/local-ci-agent/
Optional: CI_AGENT_MAX_ROUNDS=120 (default). Ctrl-C stops the launcher.
On no progress, environment failure or dirty working tree, stops nonzero.
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
MAX_ROUNDS="${CI_AGENT_MAX_ROUNDS:-120}"
OUT="${CI_AGENT_LOG_DIR:-$PWD/playtest-results/local-ci-agent}"
[[ "$MAX_ROUNDS" =~ ^[1-9][0-9]*$ ]] || {
    echo "CI_AGENT_ERROR: CI_AGENT_MAX_ROUNDS must be positive" >&2; exit 2;
}
[[ -x "$PYTHON" ]] || { echo "CI_AGENT_ERROR: .venv Python missing at $PYTHON" >&2; exit 2; }
command -v "$CODEX" >/dev/null 2>&1 || {
    echo "CI_AGENT_ERROR: Codex CLI missing; install it and log in first" >&2; exit 2;
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
if "$CODEX" exec --help 2>&1 | grep -q -- '--approve-for-me'; then
    # Recent CLI releases can automatically review workspace-write approvals,
    # including Git operations, without opening an interactive dialog.
    CODEX_POLICY=(--approve-for-me)
fi

# Each turn is an independent Codex invocation. Git commits and a checked-in
# scope registry preserve progress across context windows or CLI restarts.
# The launcher runs full CI itself, outside Codex's filesystem sandbox.
run_agent() {
    local turn="$1" task="$2" before="$3" code=0
    local prompt_file="$OUT/turn-$turn.prompt.txt"
    local log_file="$OUT/turn-$turn.codex.log"
    local summary_file="$OUT/turn-$turn.summary.txt"
    printf '%s\n' "$task" > "$prompt_file"
    echo "CI_AGENT_TURN_START: $turn revision=$before"
    # Current Codex CLI: automatic approval review with a workspace-write
    # sandbox, not unsandboxed arbitrary execution.
    if "$CODEX" exec "${CODEX_POLICY[@]}" -C "$PWD" \
            --output-last-message "$summary_file" "$task" \
            2>&1 | tee "$log_file"; then
        code=0
    else
        code=${PIPESTATUS[0]}
    fi
    if [[ "$code" -ne 0 ]]; then
        echo "CI_AGENT_STOP: Codex turn $turn failed ($code); $log_file" >&2
        exit "$code"
    fi
    ensure_main_clean
    if [[ "$(git rev-parse HEAD)" == "$before" ]]; then
        echo "CI_AGENT_STOP: no committed progress in turn $turn; $log_file" >&2
        exit 3
    fi
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
# does not discard previous Codex summaries or independent shard evidence.
counter="$OUT/round-counter"
round=0
if [[ -f "$counter" ]]; then
    round="$(cat "$counter")"
    [[ "$round" =~ ^[0-9]+$ ]] || {
        echo "CI_AGENT_ERROR: invalid $counter" >&2; exit 2;
    }
fi
attempts=0
while ((attempts < MAX_ROUNDS)); do
    attempts=$((attempts + 1))
    round=$((round + 1))
    printf '%s\n' "$round" > "$counter"
    ensure_main_clean
    before="$(git rev-parse HEAD)"

    if ! scope_complete; then
        echo "CI_AGENT_PHASE_A: current-test scope audit, round $round"
        task="You are the local repository agent for tpepels/piano_teacher. Read AGENTS.md and ROADMAP.md. PHASE A ONLY: inventory ALL pytest test files, 144+ Godot scripts and all .github workflow definitions using python scripts/ci-scope.py --inventory and the four-shard plan. Review each test case, native harness and workflow job against the actual current Godot + embedded Python application. Delete/rewrite only demonstrably obsolete cases, retain or fix current failures, revise smoke and quarantine references as warranted. Produce tests/ci-scope.json with schema=1, entries keyed by every remaining pytest module, Godot test script and CI workflow, each containing an existing current source path as owner and a concrete contract string. Produce docs/verification/ci-current-scope-audit.md documenting pytest, native-script and workflow review, including individual cases inside mixed modules and every removed case with reason/replacement; its own final line must be exactly Scope audit: COMPLETE only after the review is genuinely complete. Pass python scripts/ci-scope.py --check, bash scripts/ci-full.sh --plan and collection checks. Commit coherent progress directly on main, no worktrees. DO NOT start full four-shard CI and DO NOT pretend the audit is complete when unfinished. When unable to finish in one turn, commit the partial audit evidence and continue on the next agent turn. Current revision: $before. See $OUT for prior turn logs."
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
    # ci-full.sh runs 4 deterministic disjoint shards sequentially, stops at
    # the first failed shard, and records PASS only on the same clean revision.
    if ! gate full bash scripts/ci-full.sh --all; then
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
    task="You are the local repository agent for tpepels/piano_teacher. Read AGENTS.md and ROADMAP.md. PHASE B ONLY: fix the FIRST failing CURRENT application test or gate from the local log at $failure_log (gate $failure_gate), at clean main revision $before. Read the full traceback/artifacts and current implementation, establish root cause, make the smallest complete production/test correction without weakening checks or inventing legacy behavior, and run focused tests as possible. Maintain the current test-scope registry if files are added or removed. Commit the fix directly on main, no worktrees. Leave the checkout clean and return control to the launcher; it will repeat all four CI shards at the new commit. If the failure is environment-only, report the real blocker instead of claiming success. Previous agent logs: $OUT."
    run_agent "$round" "$task" "$before"
done

echo "CI_AGENT_STOP: exhausted CI_AGENT_MAX_ROUNDS=$MAX_ROUNDS for this invocation; logs in $OUT" >&2
exit 4

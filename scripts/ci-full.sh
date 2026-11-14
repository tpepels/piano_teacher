#!/usr/bin/env bash
# Complete release gate in four independently runnable, disjoint parts.
# Full suite includes slow cases. Smoke and extended gates are separate.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-$PWD/.venv/bin/python}"
SHARDS=4
mode=all
shard=""
force=0
pytest_args=()

usage() {
    cat <<'HELP'
Usage: bash scripts/ci-full.sh [--shard 1|2|3|4 | --all | --plan | --status] [--force] [-- pytest-options]

  --shard N  Run only part N, saving its full log and exit status.
  --all      Run every part (default), continuing after failed parts.
             Skip parts that already passed on this clean Git revision.
  --force    Rerun previously passing parts when used with --all.
  --plan     Print the deterministic partition before running tests.
  --status   Print the four recorded statuses for the current commit.
  --        Pass extra pytest arguments, for diagnosis only (not release-gate results).

Logs: playtest-results/ci-full/<commit>/shard-N.log (retained after cleanup)
Preserve temp artifacts explicitly with CI_FULL_KEEP_TMP=1.
HELP
}

while (($#)); do
    case "$1" in
        --shard)
            [[ $# -ge 2 ]] || { echo 'Missing --shard number' >&2; exit 2; }
            mode=shard; shard="$2"; shift 2 ;;
        --shard=*) mode=shard; shard="${1#*=}"; shift ;;
        --all) mode=all; shift ;;
        --plan) mode=plan; shift ;;
        --status) mode=status; shift ;;
        --force) force=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; pytest_args+=("$@"); break ;;
        *) echo "Unknown option: $1 (pytest options must follow --)" >&2; usage >&2; exit 2 ;;
    esac
done
if [[ "$mode" == shard && ! "$shard" =~ ^[1-4]$ ]]; then
    echo "--shard requires 1, 2, 3 or 4 (got '$shard')" >&2
    exit 2
fi
if [[ "$mode" != all && "$force" -eq 1 ]]; then
    echo '--force is only valid with --all' >&2
    exit 2
fi
if (( ${#pytest_args[@]} )) && [[ "$mode" != all && "$mode" != shard ]]; then
    echo 'Additional pytest arguments require --shard or --all' >&2
    exit 2
fi

revision="$(git rev-parse --short=12 HEAD)"
clean=1
if ! git diff --quiet || ! git diff --cached --quiet || [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
    clean=0
fi
out="${CI_FULL_RESULTS_DIR:-$PWD/playtest-results/ci-full}/$revision"
if [[ "$clean" -eq 0 ]]; then
    out="${out}-dirty"
    echo 'CI_FULL_NON_GATE: working tree is modified; logs only, no release PASS status.'
fi

status_summary() {
    local number state count=0
    for number in 1 2 3 4; do
        state='NOT RUN'
        if [[ -f "$out/shard-$number.status" ]]; then
            state="$(cat "$out/shard-$number.status")"
        fi
        if [[ "$state" == PASS ]]; then count=$((count+1)); fi
        printf 'CI_FULL_PART_%s: %-8s %s\n' "$number" "$state" "$out/shard-$number.log"
    done
    if [[ "$count" -eq "$SHARDS" && "$clean" -eq 1 ]]; then
        echo "CI_FULL_COMPLETE: PASS ($SHARDS/$SHARDS for $revision)"
        return 0
    fi
    echo "CI_FULL_COMPLETE: INCOMPLETE ($count/$SHARDS passed for $revision)"
    return 1
}
if [[ "$mode" == status ]]; then
    status_summary
    exit $?
fi

# Reclaim retained pytest-N directories left by previous versions of this
# runner. Never delete other users' files, symlinked roots, or general /tmp.
# Another pytest process may be running, so skip legacy cleanup if it is.
# This avoids tempfile.gettempdir(), which itself writes a probe file and
# fails before cleanup when the quota is already exhausted.
cleanup_legacy_pytest() {
    "$PYTHON" - <<'PY'
import getpass
import os
from pathlib import Path
import re
import shutil

base = Path(os.environ.get('TMPDIR') or '/tmp')
legacy = base / ('pytest-of-' + getpass.getuser())

def running_pytest():
    proc = Path('/proc')
    if not proc.is_dir():
        raise RuntimeError('Cannot verify active pytest processes without /proc')
    for directory in proc.iterdir():
        if not directory.name.isdigit() or int(directory.name) == os.getpid():
            continue
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            args = [part.decode(errors='replace') for part in
                    (directory / 'cmdline').read_bytes().split(bytes([0])) if part]
        except (OSError, ProcessLookupError, PermissionError):
            continue
        if (any(Path(arg).name in {'pytest', 'py.test'} for arg in args)
                or any(arg == '-m' and next_arg == 'pytest'
                       for arg, next_arg in zip(args, args[1:]))):
            return int(directory.name)
    return None

if legacy.is_symlink():
    raise RuntimeError(f'Refusing symlinked pytest temp root: {legacy}')
if legacy.is_dir():
    if legacy.stat().st_uid != os.getuid():
        raise RuntimeError(f'Refusing another user's pytest temp root: {legacy}')
    active = running_pytest()
    if active is not None:
        print(f'CI_FULL_TEMP_CLEANUP_SKIPPED: pytest PID {active} is running', flush=True)
    else:
        count = 0
        for entry in legacy.iterdir():
            if entry.name == 'pytest-current' and entry.is_symlink():
                entry.unlink(missing_ok=True)
            elif re.fullmatch(r'pytest-[0-9]+', entry.name) and entry.is_dir() and not entry.is_symlink():
                try:
                    shutil.rmtree(entry)
                    count += 1
                except FileNotFoundError:
                    pass  # concurrent full-suite preflight already cleaned it
        print(f'CI_FULL_TEMP_CLEANUP: removed {count} old pytest runs in {legacy}', flush=True)
PY
}
cleanup_legacy_pytest
export CI_FULL=1
if [[ "$mode" == plan ]]; then
    "$PYTHON" -m scripts.ci_full_shards
    exit $?
fi
# Reclaim old cache before creating release output directories: an exhausted
# user quota must not block the cleanup that is supposed to free it.
mkdir -p "$out"

# One trap cleans the currently running shard even on Ctrl-C or pytest failure.
CI_FULL_TMP=''
cleanup_full_tmp() {
    if [[ -z "$CI_FULL_TMP" || ! -d "$CI_FULL_TMP" ]]; then return; fi
    if [[ "${CI_FULL_KEEP_TMP:-0}" == 1 ]]; then
        printf 'CI_FULL_TEMP_RETAINED: %s\n' "$CI_FULL_TMP"
    else
        rm -rf -- "$CI_FULL_TMP"
    fi
    CI_FULL_TMP=''
}
trap cleanup_full_tmp EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

run_part() {
    local number="$1"
    local result=0 output="$out/shard-$number.log"
    CI_FULL_TMP="$(mktemp -d "${TMPDIR:-/tmp}/piano-teacher-ci-full-$number.XXXXXXXX")" || return 1
    if [[ "$clean" -eq 1 && ${#pytest_args[@]} -eq 0 ]]; then
        printf 'RUNNING\n' > "$out/shard-$number.status"
    fi
    echo "CI_FULL_PART_START: $number/$SHARDS ($revision)"
    # The plugin excludes other shards BEFORE pytest imports any test file.
    # The four deterministic file plans cover the full suite; no xfail or
    # slow-test filters change.
    if TMPDIR="$CI_FULL_TMP" "$PYTHON" -m pytest -q -m 'slow or not slow' -p scripts.ci_full_shards "--full-ci-shard=$number" --basetemp "$CI_FULL_TMP/pytest" tests "${pytest_args[@]}" 2>&1 | tee "$output"; then
        result=0
    else
        result=$?
    fi
    cleanup_full_tmp
    if [[ "$clean" -eq 1 && ${#pytest_args[@]} -eq 0 ]]; then
        if [[ "$result" -eq 0 && "$(git rev-parse --short=12 HEAD)" == "$revision" ]] && git diff --quiet && git diff --cached --quiet && [[ -z "$(git ls-files --others --exclude-standard)" ]]; then
            printf 'PASS\n' > "$out/shard-$number.status"
        else
            printf 'FAIL\n' > "$out/shard-$number.status"
        fi
    fi
    echo "CI_FULL_PART_DONE: $number/$SHARDS exit=$result log=$output"
    return "$result"
}

if [[ "$mode" == shard ]]; then
    if run_part "$shard"; then :; else exit $?; fi
    exit 0
fi

failed=0
for number in 1 2 3 4; do
    if [[ "$force" -eq 0 && "$clean" -eq 1 && ${#pytest_args[@]} -eq 0 && -f "$out/shard-$number.status" && "$(cat "$out/shard-$number.status")" == PASS ]]; then
        echo "CI_FULL_PART_SKIP: $number/$SHARDS already passed on $revision (use --force to rerun)"
        continue
    fi
    if run_part "$number"; then :; else failed=1; fi
done
if status_summary; then :; else failed=1; fi
exit "$failed"

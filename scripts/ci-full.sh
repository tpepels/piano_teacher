#!/usr/bin/env bash
# Release gate: the entire Python suite (25-45 minutes). Known-red tests are
# strict xfails listed in tests/quarantine.txt; anything else red fails this gate.
# Push gate is scripts/ci-smoke.sh.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"

# Old full-suite runs left retained pytest-N trees under /tmp/pytest-of-USER.
# Those trees exhausted the user's disk quota before later tests could write
# their SQLite stores or native rendering assets. Reclaim ONLY pytest's own
# numbered session directories, never general /tmp or another user's files.
# Refuse to remove anything when an independent pytest process is active.
"$PYTHON" - <<'PY'
import os
from pathlib import Path
import re
import shutil
import tempfile

base = Path(tempfile.gettempdir())
legacy = base / ("pytest-of-" + __import__("getpass").getuser())

def running_pytest():
    proc = Path("/proc")
    if not proc.is_dir():
        raise RuntimeError("Cannot verify active pytest processes without /proc")
    for directory in proc.iterdir():
        if not directory.name.isdigit() or int(directory.name) == os.getpid():
            continue
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            args = [part.decode(errors="replace") for part in
                    (directory / "cmdline").read_bytes().split(b"\\0") if part]
        except (OSError, ProcessLookupError, PermissionError):
            continue
        if (any(Path(arg).name in {"pytest", "py.test"} for arg in args)
                or any(arg == "-m" and next_arg == "pytest"
                       for arg, next_arg in zip(args, args[1:]))):
            return int(directory.name)
    return None

if legacy.is_symlink():
    raise RuntimeError(f"Refusing symlinked pytest temp root: {legacy}")
if legacy.is_dir():
    if legacy.stat().st_uid != os.getuid():
        raise RuntimeError(f"Refusing another user's pytest temp root: {legacy}")
    active = running_pytest()
    if active is not None:
        raise RuntimeError(f"Refusing to delete retained pytest temp while PID {active} is running")
    count = 0
    for entry in legacy.iterdir():
        if entry.name == "pytest-current" and entry.is_symlink():
            entry.unlink()
        elif re.fullmatch(r"pytest-[0-9]+", entry.name) and entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
            count += 1
    print(f"CI_FULL_TEMP_CLEANUP: removed {count} old pytest runs in {legacy}", flush=True)
PY

# A private temp root prevents overlap with any other pytest command and
# ensures even the 24-shard/full-renderer run does not accumulate old copies.
CI_FULL_TMP="$(mktemp -d "${TMPDIR:-/tmp}/piano-teacher-ci-full.XXXXXXXX")"
cleanup_full_tmp() {
    if [[ -n "${CI_FULL_TMP:-}" && -d "$CI_FULL_TMP" ]]; then
        rm -rf -- "$CI_FULL_TMP"
    fi
}
trap cleanup_full_tmp EXIT
export TMPDIR="$CI_FULL_TMP"
# The in-app readiness scenario fails (not skips) when it cannot run.
export CI_FULL=1
# Includes the slow corpus runs that pyproject's addopts deselect by default.
"$PYTHON" -m pytest -q -m "slow or not slow" --basetemp "$CI_FULL_TMP/pytest" tests "$@"

#!/usr/bin/env bash
# One local acceptance entry point. Never change the checkout or learner data.
# Each suite runs even if another fails; the final exit status is aggregate.
set -Eeuo pipefail
CALLER_DIR="$PWD"
cd "$(dirname "$0")/.."
ROOT="$PWD"

case "${1:-}" in
  "") mode=full ;;
  --quick) mode=quick ;;
  --visual) mode=visual ;;
  -h|--help)
    echo "Usage: bash scripts/verify.sh [--quick | --visual]"
    echo "Default: regression, native repertoire, package audit, visual 30 FPS, pacing 60 FPS."
    echo "--quick: regression and Godot behavior tests. --visual: both rendered suites."
    exit 0 ;;
  *) echo "Unknown option: $1" >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  echo "Only one mode may be selected." >&2
  exit 2
fi
# Preserve caller-relative optional inputs and interpreter overrides.
if [[ -n "${PIANO_PATHETIQUE_II_MIDI:-}" && "$PIANO_PATHETIQUE_II_MIDI" != /* ]]; then
  export PIANO_PATHETIQUE_II_MIDI="$CALLER_DIR/$PIANO_PATHETIQUE_II_MIDI"
fi
PYTHON="${PIANO_PYTHON:-${PYTHON:-$ROOT/.venv/bin/python}}"
if [[ "$PYTHON" != /* ]]; then PYTHON="$CALLER_DIR/$PYTHON"; fi
export PYTHON PIANO_PYTHON="$PYTHON"
RESULTS="${PIANO_TEST_RESULTS:-$HOME/piano-teacher-results}"
mkdir -p "$RESULTS"
RESULTS="$(realpath "$RESULTS")"
LOG="$(mktemp -d "$RESULTS/verify-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
export TMPDIR="$(mktemp -d "$LOG/scratch.XXXXXX")"
export PIANO_TEACHER_TIMING_DIAGNOSTICS=1
failed=0
cleanup() { rm -rf -- "$TMPDIR"; }
trap cleanup EXIT
git log -1 --oneline > "$LOG/revision.txt"
git status --short --branch > "$LOG/git-status.txt"
printf 'mode=%s\n' "$mode" > "$LOG/summary.txt"

run_check() {
  local name="$1"; shift
  local -a status
  printf '\n=== %s ===\n' "$name"
  # Disable errexit only for this pipeline so both command and log errors
  # are recorded without skipping the next independent suite.
  set +e
  "$@" 2>&1 | tee "$LOG/$name.log"
  status=("${PIPESTATUS[@]}")
  set -e
  printf '%s: exit=%s log=%s\n' "$name" "${status[0]}" "${status[1]}" | tee -a "$LOG/summary.txt"
  if (( status[0] != 0 || status[1] != 0 )); then failed=1; fi
}

if [[ "$mode" != visual ]]; then
  run_check regression bash scripts/test.sh --coverage
fi
if [[ "$mode" == full ]]; then
  # The existing full verifier includes the real repertoire and relocated
  # package audit. Do not rebuild/package twice from a separate script.
  run_check native bash scripts/verify-embedded-production-local.sh
fi
if [[ "$mode" != quick ]]; then
  run_check visual env PIANO_VISUAL_FPS=30 PIANO_VISUAL_PACING_ONLY=0 \
    PIANO_VISUAL_RESULTS="$LOG/visual-full" \
    bash scripts/verify-embedded-production-local.sh --visual-only
  run_check pacing env PIANO_VISUAL_FPS=60 PIANO_VISUAL_PACING_ONLY=1 \
    PIANO_VISUAL_RESULTS="$LOG/visual-pacing" \
    bash scripts/verify-embedded-production-local.sh --visual-only
fi
# Keep reports, not the disposable HOME, raw temporary captures or package.
cleanup
# Standard library zip avoids requiring an additional zip executable.
if ! python3 - "$LOG" <<'PY'
from pathlib import Path
import sys
import zipfile

root = Path(sys.argv[1])
archive = root.with_suffix(".zip")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            z.write(path, path.relative_to(root.parent))
print(f"Upload: {archive}")
PY
then
  failed=1
  echo "Could not create ZIP; reports remain at $LOG" >&2
fi
cat "$LOG/summary.txt"
echo "Results: $LOG"
exit "$failed"

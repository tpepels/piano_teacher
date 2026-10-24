#!/usr/bin/env bash
# One local command: fast regressions, then the complete native/Verovio library.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--ci" ) ]]; then
  echo "Usage: ./scripts/verify-notation.sh  (CI only: --ci)" >&2
  exit 2
fi

PYTHON="$PWD/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing environment: python -m venv .venv && .venv/bin/pip install -e '.[godot,test]'" >&2
  exit 2
fi
GODOT="$(command -v godot || command -v godot4 || true)"
if [[ -z "$GODOT" ]]; then
  echo "Missing Godot 4. Install it with: sudo pacman -S godot" >&2
  exit 2
fi

quick_checks() {
  # Explicit error propagation matters: Bash disables errexit within
  # a function used on the left of a pipeline/conditional.
  "$PYTHON" -m pytest -q \
    tests/test_native_notation_library.py \
    tests/test_connector_pixels.py \
    tests/test_phase3_scroll_pixels.py \
    tests/test_notation_diagnostic_package.py || return $?
  "$GODOT" --headless --path godot --check-only --script res://main.gd
}

# GitHub Actions deliberately stops after fast fixture/parse checks.
if [[ ${1:-} == "--ci" ]]; then
  quick_checks
  exit
fi

OUT="$PWD/notation-check-results"
mkdir -p "$OUT"
echo "Step 1/2: fast regressions and Godot validation"
if ! quick_checks 2>&1 | tee "$OUT/quick.log"; then
  echo "FAIL: fast regression checks. Fix these before starting the full library."
  echo "Log: $OUT/quick.log"
  exit 1
fi

if command -v xvfb-run >/dev/null 2>&1; then
  DISPLAY_COMMAND=(xvfb-run -a -s "-screen 0 1600x1000x24")
elif [[ -n "${DISPLAY:-}" ]]; then
  echo "xvfb-run unavailable; using the current graphical display." >&2
  DISPLAY_COMMAND=()
else
  echo "No graphical display. On Arch: sudo pacman -S xorg-server-xvfb xorg-xauth" >&2
  exit 2
fi

WORKERS="${PIANO_VERIFY_WORKERS:-7}"
if ! [[ "$WORKERS" =~ ^[1-9][0-9]*$ ]]; then
  echo "PIANO_VERIFY_WORKERS must be a positive integer." >&2
  exit 2
fi

# The same canonical comparison runs on every original measure, every hand,
# generated learning variant, and the supported MusicXML fixtures.
# Partition for bounded memory usage; a full pass needs all 24 shards.
SHARDS=24
failed=0
attempted=0
echo "Step 2/2: full native Godot / Verovio comparison (24 batches)"
echo "A failing batch stops the sweep: diagnose common errors before more captures."
for (( index=0; index<SHARDS; index++ )); do
  attempted=$((attempted+1))
  output="$OUT/shard-$index-of-$SHARDS"
  mkdir -p "$output"
  echo "Batch $((index+1))/$SHARDS: capturing and comparing notation"
  args=(--shard-index "$index" --shard-count "$SHARDS"
        --workers "$WORKERS" --out "$output")
  if [[ "${PIANO_VERIFY_REUSE:-0}" == 1 ]]; then
    args+=(--reuse-captures)
  fi
  # Show per-case progress, retain diagnostics, and continue past failures.
  if LIBGL_ALWAYS_SOFTWARE=1 "${DISPLAY_COMMAND[@]}" \
      "$PYTHON" -u scripts/check_native_verovio_overlay.py \
      "${args[@]}" 2>&1 | tee "$output/run.log"; then
    echo "Batch $((index+1))/$SHARDS: PASS"
  else
    echo "Batch $((index+1))/$SHARDS: FAIL (details: $output/run.log)"
    failed=$((failed+1))
    if [[ "${PIANO_VERIFY_CONTINUE_ON_FAILURE:-0}" != 1 ]]; then
      echo "Stopping after batch $attempted/$SHARDS: at least one failed batch."
      echo "Remaining batches have NOT been checked. Fix common errors first."
      echo "For deliberate exhaustive diagnosis set PIANO_VERIFY_CONTINUE_ON_FAILURE=1."
      "$PYTHON" scripts/package_notation_diagnostics.py "$output" "$OUT/triage.zip" || true
      break
    fi
  fi
done

echo
if (( failed == 0 && attempted == SHARDS )); then
  echo "PASS: fast checks and all $SHARDS Verovio/native comparison batches."
else
  echo "FAIL: $failed failed among $attempted/$SHARDS attempted batches."
  echo "Failure details are in $OUT/shard-*/run.log"
fi
echo "All logs and captures: $OUT"
(( failed == 0 && attempted == SHARDS ))

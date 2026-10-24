#!/usr/bin/env bash
# One entry point for the existing Godot-versus-Verovio verification.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

usage() {
  cat <<'HELP'
Piano Teacher notation verification

  ./scripts/verify-notation.sh quick
      Fast source/pixel regressions and Godot script validation.
  ./scripts/verify-notation.sh case chopin-5-6-both
      A named, focused real-Godot/Verovio case.
  ./scripts/verify-notation.sh file Danny_Boy
      Every measure, hand and learning variant of matching MIDI file(s).
  ./scripts/verify-notation.sh shard 0 [24]
      One deterministic batch of the complete corpus (zero-based index).
  ./scripts/verify-notation.sh full [24]
      All batches sequentially, continuing after failures.

Settings:
  PIANO_VERIFY_WORKERS=2     Godot capture workers (default: 2).
  PIANO_VERIFY_OUT=<path>    Logs and failure evidence directory.
  PIANO_VERIFY_REUSE=1       Recheck retained captures when inputs match.

Outputs are kept in notation-check-results/ (gitignored).
Use 'grep "^FAIL " notation-check-results/*/run.log' for failure headlines.
On Arch, install: sudo pacman -S --needed godot xorg-server-xvfb xorg-xauth
HELP
}

if [[ $# -eq 0 ]]; then
  usage
  exit 0
fi

mode="$1"
shift
PYTHON="$PWD/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing .venv. Run: python -m venv .venv && .venv/bin/pip install -e '.[godot,test]'" >&2
  exit 2
fi
GODOT="$(command -v godot || command -v godot4 || true)"
if [[ -z "$GODOT" ]]; then
  echo "Godot 4 not found. On Arch: sudo pacman -S godot" >&2
  exit 2
fi

if [[ "$mode" == quick ]]; then
  if [[ $# -ne 0 ]]; then
    usage >&2
    exit 2
  fi
  "$PYTHON" -m pytest -q \
    tests/test_native_notation_library.py \
    tests/test_connector_pixels.py \
    tests/test_phase3_scroll_pixels.py
  "$GODOT" --headless --path godot --check-only --script res://main.gd
  exit
fi

if command -v xvfb-run >/dev/null 2>&1; then
  DISPLAY_COMMAND=(xvfb-run -a -s "-screen 0 1600x1000x24")
elif [[ -n "${DISPLAY:-}" ]]; then
  echo "xvfb-run missing; using your current display. For reproducible captures install xorg-server-xvfb xorg-xauth." >&2
  DISPLAY_COMMAND=()
else
  echo "No display or xvfb-run; install: sudo pacman -S xorg-server-xvfb xorg-xauth" >&2
  exit 2
fi

WORKERS="${PIANO_VERIFY_WORKERS:-2}"
if ! [[ "$WORKERS" =~ ^[1-9][0-9]*$ ]]; then
  echo "PIANO_VERIFY_WORKERS must be a positive integer" >&2
  exit 2
fi
OUTPUT_ROOT="${PIANO_VERIFY_OUT:-$PWD/notation-check-results}"
mkdir -p "$OUTPUT_ROOT"

run_comparison() {
  local name="$1"
  shift
  local output="$OUTPUT_ROOT/$name"
  mkdir -p "$output"
  local args=("--workers" "$WORKERS" "--out" "$output")
  if [[ "${PIANO_VERIFY_REUSE:-0}" == 1 ]]; then
    args+=("--reuse-captures")
  fi
  echo "Verification: $name | workers=$WORKERS | output=$output"
  local status
  set +e
  LIBGL_ALWAYS_SOFTWARE=1 "${DISPLAY_COMMAND[@]}" \
    "$PYTHON" -u scripts/check_native_verovio_overlay.py \
    "${args[@]}" "$@" 2>&1 | tee "$output/run.log"
  status="${PIPESTATUS[0]}"
  set -e
  echo "$name: $([[ $status -eq 0 ]] && echo PASS || echo FAIL) | log: $output/run.log"
  return "$status"
}

case "$mode" in
  case)
    if [[ $# -ne 1 ]]; then usage >&2; exit 2; fi
    safe="$(printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_')"
    run_comparison "case-$safe" --case "$1"
    ;;
  file)
    if [[ $# -ne 1 ]]; then usage >&2; exit 2; fi
    safe="$(printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_')"
    run_comparison "file-$safe" --only "$1"
    ;;
  shard)
    if [[ $# -lt 1 || $# -gt 2 ]]; then usage >&2; exit 2; fi
    index="$1"
    count="${2:-24}"
    if ! [[ "$index" =~ ^(0|[1-9][0-9]*)$ && "$count" =~ ^[1-9][0-9]*$ ]] || (( index >= count )); then
      echo "Expected shard INDEX COUNT where 0 <= INDEX < COUNT" >&2
      exit 2
    fi
    run_comparison "shard-$index-of-$count" --shard-index "$index" --shard-count "$count"
    ;;
  full)
    if [[ $# -gt 1 ]]; then usage >&2; exit 2; fi
    count="${1:-24}"
    if ! [[ "$count" =~ ^[1-9][0-9]*$ ]]; then
      echo "Expected a positive shard count" >&2
      exit 2
    fi
    failed=0
    for (( index=0; index<count; index++ )); do
      if ! run_comparison "shard-$index-of-$count" --shard-index "$index" --shard-count "$count"; then
        failed=$((failed+1))
      fi
    done
    echo "Complete corpus: $((count-failed))/$count batches passed. Evidence: $OUTPUT_ROOT"
    (( failed == 0 ))
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
# One local command: fast regressions, then the complete native/Verovio library.
# Parse the entire driver before starting long-running commands. Editing this
# file during a sweep must not splice new bytes into Bash's next top-level read.
main() {
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
    tests/test_fingering_provider.py \
    tests/test_fingering_annotations.py \
    tests/test_fingering_real_pieces.py \
    tests/test_fingering_backend.py \
    tests/test_native_fingering.py \
    tests/test_fingering_real_placement.py \
    tests/test_fingering_obstacle_geometry.py \
    tests/test_fingering_placement_metadata.py \
    tests/test_canonical_fingering_isolation.py \
    tests/test_practice_timeline.py \
    tests/test_preprocessing_cache.py \
    tests/test_piano_register_engraving.py \
    tests/test_native_display_hand.py \
    tests/test_peace_piece_pixels.py \
    tests/test_continuous_practice_loop.py \
    tests/test_continuous_repeat_pixels.py \
    tests/test_repeat_transport_pixels.py \
    tests/test_repeat_recovery_context_pixels.py \
    tests/test_visible_playback.py::test_visible_playback_rejects_native_fallback_warning \
    tests/test_visible_playback.py::test_native_sampling_tracks_one_occurrence_when_next_repeat_is_visible \
    tests/test_native_notation_library.py \
    tests/test_connector_pixels.py \
    tests/test_phase3_scroll_pixels.py \
    tests/test_notation_diagnostic_package.py \
    tests/test_native_audit_recovery.py \
    tests/test_verify_notation_recovery.py \
    tests/test_verification_runner_failures.py \
    tests/test_joint_registration_resources.py \
    tests/test_connector_source_layers.py \
    tests/test_extra_symbol_shard_regressions.py \
    tests/test_rest_dot_retained_pixels.py \
    tests/test_polyphonic_stem_pixels.py \
    tests/test_native_voice_collisions.py \
    tests/test_moonlight_tuplet_pixels.py \
    tests/test_extra_symbol_pixels.py::test_real_playhead_overlap_is_ambiguous_without_exempting_detached_heads || return $?
  "$GODOT" --headless --path godot --check-only --script res://main.gd
}

# GitHub Actions deliberately stops after fast fixture/parse checks.
if [[ ${1:-} == "--ci" ]]; then
  quick_checks
  exit
fi

OUT="$PWD/notation-check-results"
mkdir -p "$OUT"
audit_pid=""
output="$OUT"
failed_output=""
first_signal_status=0
signal_count=0
record_signal() {
  if (( first_signal_status == 0 )); then
    first_signal_status=$1
  fi
  signal_count=$((signal_count+1))
}
package_on_exit() {
  local exit_status=$?
  local diagnostic_output="${failed_output:-$output}"
  # EXIT owns the only package attempt. Keep handling signals without
  # re-entering stop_current or abandoning the child publishing the ZIP.
  trap 'record_signal 130' INT
  trap 'record_signal 143' TERM
  if (( exit_status != 0 )) && [[ -n "$diagnostic_output" && -d "$diagnostic_output" ]]; then
    "$PYTHON" scripts/package_notation_diagnostics.py "$diagnostic_output" "$OUT/triage.zip" --publication-status &
    local package_pid=$!
    local package_status=0
    local observed_signals
    while true; do
      observed_signals=$signal_count
      if wait "$package_pid"; then
        package_status=0
      else
        package_status=$?
      fi
      # A trapped signal interrupts Bash's wait before the child finishes.
      # Wait again, even if the child exited concurrently with that signal.
      if (( signal_count == observed_signals )); then
        break
      fi
    done
    if (( package_status != 0 )); then
      echo "Could not package diagnostics; original failure status: $exit_status" >&2
    fi
  fi
  if (( first_signal_status != 0 )); then
    exit_status=$first_signal_status
  fi
  trap - EXIT
  exit "$exit_status"
}
stop_current() {
  record_signal "$1"
  failed_output="$output"
  trap 'record_signal 130' INT
  trap 'record_signal 143' TERM
  if [[ -n "$audit_pid" ]]; then
    # The batch has its own session. The Python coordinator handles TERM,
    # checkpoints partial progress and terminates its owned Godot workers.
    kill -TERM -- "-$audit_pid" 2>/dev/null || true
    for (( retry=0; retry<50; retry++ )); do
      kill -0 "$audit_pid" 2>/dev/null || break
      sleep .1
    done
    kill -KILL -- "-$audit_pid" 2>/dev/null || true
    wait "$audit_pid" 2>/dev/null || true
  fi
  echo "Interrupted: completed case checkpoints and captures are retained."
  exit "$first_signal_status"
}
trap package_on_exit EXIT
trap 'stop_current 130' INT
trap 'stop_current 143' TERM
echo "Step 1/2: fast regressions and Godot validation"
if quick_checks 2>&1 | tee "$OUT/quick.log"; then
  :
else
  quick_status=$?
  echo "FAIL: fast regression checks. Fix these before starting the full library."
  echo "Log: $OUT/quick.log"
  exit "$quick_status"
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

WORKERS="${PIANO_VERIFY_WORKERS:-2}"
if ! [[ "$WORKERS" =~ ^[1-9][0-9]*$ ]]; then
  echo "PIANO_VERIFY_WORKERS must be a positive integer." >&2
  exit 2
fi

# The same canonical comparison runs on every original measure, every hand,
# generated learning variant, and the supported MusicXML fixtures.
# Partition for bounded memory usage; a full pass needs all 24 shards.
SHARDS=24
failed=0
failed_status=0
attempted=0
echo "Step 2/2: full native Godot / Verovio comparison (24 batches)"
echo "A failing batch stops the sweep: diagnose common errors before more captures."
for (( index=0; index<SHARDS; index++ )); do
  attempted=$((attempted+1))
  output="$OUT/shard-$index-of-$SHARDS"
  mkdir -p "$output"
  echo "Batch $((index+1))/$SHARDS: capturing and comparing notation"
  # The outer EXIT handler packages after the log writer has flushed, including
  # coordinator crashes. Standalone coordinator commands package themselves.
  args=(--no-package-diagnostics --shard-index "$index" --shard-count "$SHARDS"
        --workers "$WORKERS" --out "$output"
        --case-timeout "${PIANO_VERIFY_CASE_TIMEOUT:-600}"
        --worker-memory-mib "${PIANO_VERIFY_MEMORY_MIB:-3072}")
  if [[ "${PIANO_VERIFY_RESUME:-1}" == 1 ]]; then
    args+=(--resume)
  fi
  if [[ "${PIANO_VERIFY_REUSE:-1}" == 1 ]]; then
    args+=(--reuse-captures)
  fi
  # Retain earlier attempts' logs. The coordinator writes atomic checkpoints
  # per completed case, so the same command resumes after an interruption.
  setsid env LIBGL_ALWAYS_SOFTWARE=1 "${DISPLAY_COMMAND[@]}" \
      "$PYTHON" -u scripts/check_native_verovio_overlay.py "${args[@]}" \
      > >(tee -a "$output/run.log") 2>&1 &
  audit_pid=$!
  if wait "$audit_pid"; then
    audit_status=0
  else
    audit_status=$?
  fi
  audit_pid=""
  wait || true # Flush the log writer before packaging its last lines.
  if (( audit_status == 0 )); then
    echo "Batch $((index+1))/$SHARDS: PASS"
  else
    echo "Batch $((index+1))/$SHARDS: FAIL (details: $output/run.log)"
    if [[ -z "$failed_output" ]]; then
      failed_output="$output"
      failed_status="$audit_status"
    fi
    failed=$((failed+1))
    if [[ "${PIANO_VERIFY_CONTINUE_ON_FAILURE:-0}" != 1 ]]; then
      echo "Stopping after batch $attempted/$SHARDS: at least one failed batch."
      echo "Remaining batches have NOT been checked. Fix common errors first."
      echo "For deliberate exhaustive diagnosis set PIANO_VERIFY_CONTINUE_ON_FAILURE=1."
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
exit "$failed_status"
}

main "$@"

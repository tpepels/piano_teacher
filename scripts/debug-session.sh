#!/usr/bin/env bash
# Start the app normally and record a debug log of the session: every state
# change, every Free target with what the staff draws, MIDI input, and a staff
# heartbeat each second. Afterwards the log path is printed; share it.
# Usage: bash scripts/debug-session.sh [app args...]
set -Eeuo pipefail
cd "$(dirname "$0")/.."
dir="$PWD/debug-sessions"
mkdir -p "$dir"
stamp="$(date +%Y-%m-%d_%H-%M-%S)"
export PIANO_DEBUG_LOG="$dir/$stamp-state.log"
export PIANO_TEACHER_TIMING_DIAGNOSTICS=1
console="$dir/$stamp-console.log"
echo "Debug session: $PIANO_DEBUG_LOG"
status=0
bash run.sh "$@" 2>&1 | tee "$console" || status=$?
echo
echo "Debug logs:"
echo "  $PIANO_DEBUG_LOG"
echo "  $console"
exit "$status"

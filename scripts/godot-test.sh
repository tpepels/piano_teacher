#!/usr/bin/env bash
# Run one Godot test command and fail on what Godot reports but does not
# return: Godot exits 0 after a SCRIPT ERROR, a parse error, a script that
# failed to load, or a test that printed a nonzero <NAME>_FAILURES count.
# Usage: scripts/godot-test.sh <timeout> <godot args...>
set -uo pipefail
limit="$1"; shift
binary="${GODOT_BIN:-$(command -v godot || command -v godot4)}"
output="$(timeout "$limit" "$binary" "$@" 2>&1)"
status=$?
printf '%s\n' "$output"
if [[ $status -ne 0 ]]; then
  echo "godot-test: exit status $status" >&2
  exit "$status"
fi
if grep -qE 'SCRIPT ERROR|Parse Error|ERROR: Failed to load script' <<<"$output"; then
  echo "godot-test: Godot reported a script error" >&2
  exit 1
fi
if grep -qE '_FAILURES:[[:space:]]*[1-9]' <<<"$output"; then
  echo "godot-test: the test reported failures" >&2
  exit 1
fi

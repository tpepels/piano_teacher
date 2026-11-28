#!/usr/bin/env bash
# Small player-behavior checks using the production Godot owners.
# These semantic/head-record fixtures do not establish piano acceptance.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
export PIANO_TEST_SCORE_BUNDLE="$fixture/score.json"
"${PYTHON:-$PWD/.venv/bin/python}" tests/godot/prepare_score_bundle.py "$PIANO_TEST_SCORE_BUNDLE"
failed=0
for scenario in score_readiness practice_controls score_stream authorized_timeline note_feedback; do
  echo "Checking Godot player behavior: $scenario"
  if ! bash scripts/godot-test.sh 55s --headless --path godot \
    --script "$PWD/tests/godot/$scenario.gd"; then
    failed=1
  fi
done
if (( failed )); then
  exit 1
fi
echo "GODOT_PLAYER_BEHAVIOR_OK"

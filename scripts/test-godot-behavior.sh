#!/usr/bin/env bash
# Small player-behavior checks using the production Godot owners.
# These semantic/head-record fixtures do not establish piano acceptance.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
for scenario in practice_controls score_stream authorized_timeline note_feedback score_readiness; do
  echo "Checking Godot player behavior: $scenario"
  bash scripts/godot-test.sh 20s --headless --path godot \
    --script "$PWD/tests/godot/$scenario.gd"
done
echo "GODOT_PLAYER_BEHAVIOR_OK"

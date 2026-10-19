#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if command -v godot >/dev/null 2>&1; then
  GODOT=godot
elif command -v godot4 >/dev/null 2>&1; then
  GODOT=godot4
else
  echo "Godot 4 not found: install Godot to validate main.gd" >&2
  exit 1
fi
"$GODOT" --headless --path godot --check-only --script res://main.gd
# Phase 1's clock-locked camera must be exact even at negative count-in beats.
"$GODOT" --headless --path godot --script "$PWD/tests/godot/score_beat_camera.gd"
# Layout is executable Godot behavior, not a Python-only geometry simulation.
bash scripts/check_phase2_ui.sh

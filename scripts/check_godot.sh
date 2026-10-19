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
# The clocked production camera was reverted; retain the source-pixel
# integrity and explicit complete-passage fallback regression.
"$GODOT" --headless --path godot --script "$PWD/tests/godot/score_exact_spacing.gd"
# Layout is executable Godot behavior, not a Python-only geometry simulation.
bash scripts/check_phase2_ui.sh

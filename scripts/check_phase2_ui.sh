#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if command -v godot >/dev/null 2>&1; then
  GODOT=godot
elif command -v godot4 >/dev/null 2>&1; then
  GODOT=godot4
else
  echo "Godot 4 is required for UI layout verification" >&2
  exit 1
fi
for geometry in 1536x960 1024x768 800x600; do
  echo "Checking Godot practice layout at ${geometry}"
  "${GODOT}" --headless --path godot --script res://ui_layout_smoke.gd -- "${geometry}"
done

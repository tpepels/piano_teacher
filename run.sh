#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if command -v godot >/dev/null 2>&1; then
  GODOT=godot
elif command -v godot4 >/dev/null 2>&1; then
  GODOT=godot4
else
  echo "Godot 4 is required. On Arch: sudo pacman -S godot" >&2
  exit 1
fi
python -m piano_teacher.server &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT
"$GODOT" --path godot

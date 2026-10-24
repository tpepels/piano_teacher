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
# Exercise the sole production view with real native assets and revision gates.
PYTHON="$PWD/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi
"$PYTHON" -m pytest -q tests/test_native_production.py tests/test_phase_c_notation.py
# Layout is executable Godot behavior, not a Python-only geometry simulation.
bash scripts/check_phase2_ui.sh

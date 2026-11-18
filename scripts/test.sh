#!/usr/bin/env bash
# The whole test suite: core Python tests, then the Godot parse/UI check.
# Usage: bash scripts/test.sh [--python-only] [pytest args...]
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-$PWD/.venv/bin/python}"
python_only=0
if [[ "${1:-}" == "--python-only" ]]; then python_only=1; shift; fi
"$PYTHON" -m pytest -q "$@"
if (( ! python_only )); then
  bash scripts/check-godot-syntax.sh
fi

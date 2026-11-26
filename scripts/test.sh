#!/usr/bin/env bash
# CI behavior tests, followed by Godot parsing and native behavior scenarios.
# Usage: bash scripts/test.sh [--python-only] [--coverage] [pytest args...]
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-$PWD/.venv/bin/python}"
python_only=0
coverage=0
while (( $# )); do
  case "$1" in
    --python-only) python_only=1; shift ;;
    --coverage) coverage=1; shift ;;
    *) break ;;
  esac
done
if (( coverage )); then
  "$PYTHON" -m coverage run --branch --source=piano_teacher -m pytest -q "$@"
  "$PYTHON" -m coverage xml -o coverage.xml
  "$PYTHON" -m coverage json -o coverage.json
  "$PYTHON" -c 'import json; t=json.load(open("coverage.json"))["totals"]; print("Python coverage: %.1f%% lines, %.1f%% branches" % (t["percent_statements_covered"], t["percent_branches_covered"]))'
  echo "Python coverage is informational; it does not measure Godot or physical acceptance."
else
  "$PYTHON" -m pytest -q "$@"
fi
if (( ! python_only )); then
  bash scripts/check-godot-syntax.sh
  PYTHON="$PYTHON" bash scripts/test-godot-behavior.sh
fi

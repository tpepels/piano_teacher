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
  (
    trace_dir=$(mktemp -d)
    trap 'rm -rf "$trace_dir"' EXIT
    cat > "$trace_dir/coverage.ini" <<'EOF'
[run]
branch = True
parallel = True
source = piano_teacher
EOF
    # The real score worker starts with -S, so it skips sitecustomize.
    # Instrument its exec in coverage runs through the interpreter override.
    cat > "$trace_dir/score-python" <<'EOF'
#!/bin/sh
if [ "$1" = -S ] && [ "$2" = -c ]; then
  bootstrap=$3
  shift 3
  exec "$PIANO_COVERAGE_PYTHON" -S -c "import coverage; coverage.process_startup(); $bootstrap" "$@"
fi
exec "$PIANO_COVERAGE_PYTHON" "$@"
EOF
    chmod +x "$trace_dir/score-python"
    PIANO_COVERAGE_PYTHON="$PYTHON" PIANO_PYTHON="$trace_dir/score-python" \
      COVERAGE_PROCESS_START="$trace_dir/coverage.ini" COVERAGE_FILE="$trace_dir/.coverage" \
      "$PYTHON" -m coverage run --rcfile="$trace_dir/coverage.ini" -m pytest -q "$@"
    "$PYTHON" -m coverage combine --quiet "$trace_dir"
  )
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

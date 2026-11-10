#!/usr/bin/env bash
# Release gate: the entire Python suite (25-45 minutes). Known-red tests are
# strict xfails listed in tests/quarantine.txt; anything else red fails this gate.
# Push gate is scripts/ci-smoke.sh.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
exec "$PYTHON" -m pytest -q tests "$@"

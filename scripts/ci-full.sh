#!/usr/bin/env bash
# Release gate: the entire Python suite (25-45 minutes). Known-red tests are
# strict xfails listed in tests/quarantine.txt; anything else red fails this gate.
# Push gate is scripts/ci-smoke.sh.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
# The in-app readiness scenario fails (not skips) when it cannot run.
export CI_FULL=1
# Includes the slow corpus runs that pyproject's addopts deselect by default.
exec "$PYTHON" -m pytest -q -m "slow or not slow" tests "$@"

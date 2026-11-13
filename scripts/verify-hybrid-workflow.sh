#!/usr/bin/env bash
# Bounded local acceptance checks for the complete MIDI Coda/Fukuda pathway.
# Does not start GitHub Actions or wait for any remote CI job.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  PY="${PYTHON:-python3}"
fi

MODE="${1:---focused}"
if [[ "$MODE" != "--focused" && "$MODE" != "--corpus" && "$MODE" != "--all" ]]; then
  echo "Usage: $0 [--focused|--corpus|--all]" >&2
  exit 2
fi

if [[ "$MODE" != "--corpus" ]]; then
  timeout 90s "$PY" -m pytest -q --tb=short \
    tests/test_adaptive_hybrid_journey.py \
    tests/test_composed_midi_lessons.py \
    tests/test_lesson_generator_architecture.py \
    tests/test_course_consolidation.py \
    tests/test_fukuda_midi_phase4.py \
    tests/test_midi_stage_wiring.py \
    tests/test_strategy_handoff.py \
    tests/test_state_projection.py \
    tests/test_runtime_architecture_contract.py \
    tests/test_phase5_architecture_audit.py \
    tests/test_inprocess_dispatcher.py \
    tests/test_phase6_inprocess.py \
    tests/test_mastered_stage_replanning.py
  if [[ -n "${GODOT_BIN:-}" ]]; then
    binary="$GODOT_BIN"
  elif command -v godot >/dev/null 2>&1; then
    binary="$(command -v godot)"
  elif command -v godot4 >/dev/null 2>&1; then
    binary="$(command -v godot4)"
  else
    binary=""
  fi
  if [[ -n "$binary" ]]; then
    for fixture in continuous_score_flow score_stream_admission lesson_stage_picker; do
      GODOT_BIN="$binary" bash scripts/godot-test.sh 25s --headless --path godot \
        --script "$PWD/tests/godot/$fixture.gd"
    done
    GODOT_BIN="$binary" bash scripts/godot-test.sh 25s --headless --path godot \
      --script "$PWD/tests/godot/settings_ownership.gd" -- preferences
  else
    echo "GODOT_HYBRID_SKIPPED: Godot binary not installed" >&2
  fi
fi

if [[ "$MODE" == "--corpus" || "$MODE" == "--all" ]]; then
  timeout 150s "$PY" -m pytest -q --tb=short \
    tests/test_composed_midi_repertoire.py
fi

echo "Hybrid MIDI software verification finished."
echo "Physical Bluetooth/USB keyboard testing remains separate."

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
    tests/test_fukuda_midi_phase4.py \
    tests/test_coda_piece_curriculum.py \
    tests/test_midi_stage_wiring.py \
    tests/test_state_projection.py
  if command -v godot >/dev/null 2>&1; then
    timeout 25s godot --headless --path godot --script \
      res://../tests/godot/idle_note_preview.gd
  else
    echo "GODOT_IDLE_PREVIEW_SKIPPED: Godot binary not installed" >&2
  fi
fi

if [[ "$MODE" == "--corpus" || "$MODE" == "--all" ]]; then
  timeout 150s "$PY" -m pytest -q --tb=short \
    tests/test_composed_midi_repertoire.py
fi

echo "Hybrid MIDI software verification finished."
echo "Physical Bluetooth/USB keyboard testing remains separate."

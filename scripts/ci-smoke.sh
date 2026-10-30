#!/usr/bin/env bash
# Automatic push CI only: cheap Python contracts with a hard deadline.
# No Godot rasterization, full notation corpus, ONNX, or model installation.
# Broader scenarios belong to explicit-only scripts/ci-extended.sh.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python}"
"$PYTHON" -m compileall -q piano_teacher tests scripts
find scripts -type f -name '*.sh' -print0 | xargs -0 -r bash -n
# Focused, self-contained MIDI and state/assessment contracts.
timeout 25s "$PYTHON" -m pytest -q \
  tests/test_midi_connection.py \
  tests/test_rolling_recovery_transition.py \
  tests/test_assessment_service.py \
  tests/test_state_projection.py \
  tests/test_exercise_contracts.py \
  tests/test_exercise_strategies.py \
  tests/test_timing_live_integration.py \
  tests/test_strategy_pipeline.py \
  tests/test_timed_real_scores_and_recovery.py \
  tests/test_step4_algorithms.py \
  tests/test_step4_real_scores.py \
  tests/test_rubricnet_reproduction.py \
  tests/test_rubricnet_offline_integration.py \
  tests/test_moonlight_real_midi_beams.py \
  tests/test_coda_matrix_research.py \
  tests/test_coda_written_rests_research.py

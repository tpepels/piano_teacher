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
  tests/test_practice_warning_policy.py \
  tests/test_live_input_index.py \
  tests/test_engine_command_errors.py \
  tests/test_library_api.py \
  tests/test_frontend_startup.py \
  tests/test_phase0_smoke.py \
  tests/test_inprocess_dispatcher.py \
  tests/test_inprocess_artifact_install.py \
  tests/test_inprocess_transport_structure.py \
  tests/test_godot_preload_paths.py \
  tests/test_midi_polyphonic_stems.py \
  tests/test_midi_visual_fast_path.py \
  tests/test_midi_calibration.py \
  tests/test_forgiving_midi_practice.py \
  tests/test_midi_only_product.py \
  tests/test_library.py \
  tests/test_midi_connection.py \
  tests/test_rolling_recovery_transition.py \
  tests/test_continuous_practice_loop.py::test_coda_practice_finishes_before_adaptive_retry_or_guided_switch \
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
  tests/test_shared_tempo_timeline.py \
  tests/test_live_input_view.py \
  tests/test_notation_coverage_report.py

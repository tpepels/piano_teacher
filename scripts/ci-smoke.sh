#!/usr/bin/env bash
# Automatic CI: contracts and parse checks only, with strict time bounds.
# Full rendering regression suite remains in verify-notation.sh --ci.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-$PWD/.venv/bin/python}"
GODOT="$(command -v godot || command -v godot4)"
"$PYTHON" -m compileall -q piano_teacher
# Stable non-corpus boundaries: persistence, assessment, transport, UI and
# independent notation layout. Real pixel/corpus runs are intentionally excluded.
timeout 105s "$PYTHON" -m pytest -q \
  tests/test_completion_route.py \
  tests/test_completion_handlers.py \
  tests/test_control_dispatch_refactor.py \
  tests/test_engine_update_refactor.py \
  tests/test_progress_repository.py \
  tests/test_assessment_service.py \
  tests/test_visual_transport.py \
  tests/test_state_projection.py \
  tests/test_transport_projection.py \
  tests/test_recovery_projection.py \
  tests/test_ink_spacing.py \
  tests/test_source_measure_picker.py \
  tests/test_settings_screen.py \
  tests/test_performance_review_strip.py \
  tests/test_native_voice_layout.py \
  tests/test_rest_lane_layout.py \
  tests/test_fingering_spatial_layout.py \
  tests/test_script_permissions.py
timeout 25s "$GODOT" --headless --path godot --check-only --script res://main.gd

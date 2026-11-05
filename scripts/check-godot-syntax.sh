#!/usr/bin/env bash
# Fast Godot 4.7 parser validation. Never starts the UI, backend or MIDI.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
if [[ -n "${GODOT_BIN:-}" ]]; then
  binary="$GODOT_BIN"
elif command -v godot >/dev/null 2>&1; then
  binary="$(command -v godot)"
elif command -v godot4 >/dev/null 2>&1; then
  binary="$(command -v godot4)"
else
  echo "Godot 4.7 binary not available; cannot validate GDScript" >&2
  exit 1
fi
for script in \
  res://main.gd \
  res://practice_screen.gd \
  res://practice_score_stage.gd \
  res://tempo_vocabulary.gd \
  res://mint_glow_field.gd \
  res://settings_screen.gd \
  res://practice_frame_coordinator.gd \
  res://continuous_score_flow.gd \
  res://lesson_screen.gd \
  res://practice_state_presenter.gd \
  res://command_failure_presenter.gd \
  res://command_success_policy.gd \
  res://command_success_presenter.gd \
  res://command_success_effects.gd \
  res://practice_control_policy.gd \
  res://metronome_frame_coordinator.gd \
  res://command_request_state.gd \
  res://navigation_policy.gd \
  res://live_midi_feedback.gd \
  res://notation/native/view.gd \
  res://inprocess_bus.gd \
  res://native_bridge_smoke.gd \
  res://production_ui_smoke.gd \
  res://production_session_journey.gd \
  res://inprocess_request.gd \
  res://score_asset_queue.gd \
  res://score_asset_session.gd \
  res://score_runway.gd \
  res://score_step_timeline.gd \
  res://demo_player.gd \
  res://library_catalog_coordinator.gd \
  res://midi_device_coordinator.gd; do
  echo "Checking $script"
  output=$(timeout 12s "$binary" --headless --path godot --check-only --script "$script" 2>&1) || {
    printf '%s\n' "$output"
    exit 1
  }
  printf '%s\n' "$output"
  # Godot can return zero even when transitive preloads fail to compile.
  if [[ "$output" == *"SCRIPT ERROR:"* ||
        "$output" == *"ERROR: Failed to load script"* ]]; then
    echo "Godot reported a script compilation error in $script" >&2
    exit 1
  fi
done
# Pure SceneTree fixtures execute in-process, without MIDI, score loading or UI.
for fixture in continuous_score_flow command_success_effects command_request_state inprocess_request_lifecycle command_success_presenter practice_control_policy practice_frame_coordinator metronome_frame_coordinator calibration_beat_pulse coda_piece_strategy score_asset_lifecycle seamless_score_runway native_score_feedback; do
  echo "Checking Godot behavior: $fixture"
  timeout 12s "$binary" --headless --path godot --script "$PWD/tests/godot/$fixture.gd"
done
# Run the real Practice UI in the headless Godot harness after parsing.
for scenario in captions signals score_gate intro_markers source_picker midi_guard layout; do
  echo "Checking Practice UI: $scenario"
  timeout 15s "$binary" --headless --path godot \
    --script "$PWD/tests/godot/practice_screen.gd" -- "$scenario"
done
for scenario in preferences tempo_draft signals pickers layout; do
  echo "Checking Settings: $scenario"
  timeout 15s "$binary" --headless --path godot \
    --script "$PWD/tests/godot/settings_ownership.gd" -- "$scenario"
done
for scenario in overview choices reset layout; do
  echo "Checking Lesson Path: $scenario"
  timeout 15s "$binary" --headless --path godot \
    --script "$PWD/tests/godot/lesson_ownership.gd" -- "$scenario"
done
for contract in publication stale retry failure native; do
  echo "Checking Godot score-session contract: $contract"
  timeout 12s "$binary" --headless --path godot --script "$PWD/tests/godot/score_asset_session.gd" -- "$contract"
done
echo "GODOT_STARTUP_SYNTAX_OK"

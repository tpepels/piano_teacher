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
  res://inprocess_bus.gd \
  res://native_bridge_smoke.gd \
  res://inprocess_request.gd \
  res://score_asset_queue.gd \
  res://demo_player.gd \
  res://library_catalog_coordinator.gd \
  res://midi_device_coordinator.gd; do
  echo "Checking $script"
  timeout 12s "$binary" --headless --path godot --check-only --script "$script"
done
echo "GODOT_STARTUP_SYNTAX_OK"

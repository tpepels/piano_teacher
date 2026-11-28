#!/usr/bin/env bash
# Drive the same production worker recovery journey against source or a relocated app.
set -Eeuo pipefail
scratch="$1"
godot="$2"
project="$3"
journey="$4"
mkdir -p "$scratch"
export XDG_CONFIG_HOME="$scratch/config" XDG_DATA_HOME="$scratch/data" XDG_CACHE_HOME="$scratch/cache"
export PIANO_TEST_FINGERING_HOLD="$scratch/hold-fingering"
# Hold the real production inference call on the source lane for several
# musical tick intervals, then run the provider and return its real result.
cat > "$scratch/delayed-fingering-python" <<'SH'
#!/bin/sh
if [ -f "$PIANO_TEST_FINGERING_HOLD" ]; then
  exec "$PIANO_PYTHON" -S -c '
import os
import time
with open(os.environ["PIANO_TEST_FINGERING_HOLD"], "w") as marker:
    marker.write(str(os.getpid()))
time.sleep(4.5)
raise SystemExit(1)
  '
fi
sleep 1
exec "$PIANO_PYTHON" "$@"
SH
chmod +x "$scratch/delayed-fingering-python"
timeout 150s env PIANO_FINGERING_PYTHON="$scratch/delayed-fingering-python" \
    "$godot" --headless --audio-driver Dummy --path "$project" \
    --script "$journey"

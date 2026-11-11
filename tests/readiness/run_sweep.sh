#!/usr/bin/env bash
# R1 readiness sweep for one MIDI piece in the real application.
# Usage: tests/readiness/run_sweep.sh <midi path> <out dir> [max seconds] [WxH] [full|plain|noretry|nopause|cipause|restpause|fullrest]
# Isolated HOME/XDG dirs (real learner progress is never touched), the
# default exercise strategy, a virtual ALSA MIDI keyboard played by
# tests/readiness/pyhook/sitecustomize.py, and a real (windowed) framebuffer.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MIDI="$(realpath "$1")"
OUT="$(realpath -m "$2")"
MAX="${3:-240}"
RES="${4:-1600x900}"
SCENARIO="${5:-full}"
PYTHON="$ROOT/.venv/bin/python"
GODOT_BIN="${GODOT_BIN:-$(command -v godot || command -v godot4)}"
rm -rf "$OUT"
mkdir -p "$OUT/home/Music/Piano Teacher" "$OUT/config" "$OUT/data" "$OUT/cache"
export HOME="$OUT/home" XDG_CONFIG_HOME="$OUT/config" XDG_DATA_HOME="$OUT/data" \
  XDG_CACHE_HOME="$OUT/cache"
export PIANO_TEACHER_PYTHON_HOME="$("$PYTHON" -c 'import sys; print(sys.base_prefix)')"
PY_SITE="$("$PYTHON" -c 'import site; print(site.getsitepackages()[0])')"
PY_LIB="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
export PYTHONPATH="$ROOT/tests/readiness/pyhook:$ROOT:$PY_SITE"
[[ -n "$PY_LIB" ]] && export LD_LIBRARY_PATH="$PY_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export R1_SWEEP_DIR="$OUT"
export PIANO_TEACHER_TIMING_DIAGNOSTICS=1
NAME="$(basename "$MIDI")"
cp "$MIDI" "$HOME/Music/Piano Teacher/$NAME"
"$PYTHON" - "$NAME" <<'PY'
import sys
from piano_teacher.library import ScoreLibrary
library = ScoreLibrary()
library.mark_opened(sys.argv[1])
library.update(fullscreen=False)
print("SEEDED", sys.argv[1], library.settings.get("exercise_strategy"))
PY
uptime > "$OUT/load_before.txt"
start=$(date +%s.%N)
timeout $((MAX + 90)) "$GODOT_BIN" --path "$ROOT/godot" --windowed --resolution "$RES" \
  --audio-driver Dummy --script "$ROOT/tests/readiness/r1_sweep.gd" -- "$OUT" "$MAX" "$SCENARIO" \
  > "$OUT/godot.log" 2>&1
status=$?
end=$(date +%s.%N)
uptime > "$OUT/load_after.txt"
echo "exit=$status wall=$(python3 -c "print(round($end-$start,1))")" | tee "$OUT/exit.txt"
grep -cE 'SCRIPT ERROR|Parse Error' "$OUT/godot.log" | sed 's/^/script_errors=/' | tee -a "$OUT/exit.txt"
# The isolated library, preprocessing cache and demo audio are large; keep
# only the evidence (captures, logs, JSON).
rm -rf "${OUT:?}/home" "${OUT:?}/data" "${OUT:?}/cache" "${OUT:?}/config"

#!/usr/bin/env bash
# Local equivalent of inprocess-native-smoke.yml, including its package audit.
# Run from any directory. All lesson settings and imported MIDI fixtures are
# isolated under a temporary HOME; real learner progress is never modified.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
MODE="${1:-full}"
if [[ "$MODE" != full && "$MODE" != --without-package ]]; then
  echo "Usage: bash scripts/verify-embedded-production-local.sh [--without-package]" >&2
  exit 2
fi
PYTHON="${PIANO_PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing $PYTHON. Install Python 3.14 and .venv dependencies as in README.md." >&2
  exit 2
fi
GODOT_BIN="${GODOT_BIN:-$(command -v godot || command -v godot4 || true)}"
if [[ -z "$GODOT_BIN" || ! -x "$GODOT_BIN" ]] || \
    [[ "$("$GODOT_BIN" --version 2>/dev/null)" != 4.7.2* ]]; then
  echo "Godot 4.7.2 must be installed (or specify GODOT_BIN)." >&2
  exit 2
fi
if ! "$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3,14); import mido, rtmidi, verovio, music21, cairosvg, PIL'; then
  echo "Install Python 3.14 packages: .venv/bin/python -m pip install -e '.[godot,test]'" >&2
  exit 2
fi
if [[ "$MODE" == full ]] && ! command -v node >/dev/null 2>&1; then
  echo "A local package audit also needs Node.js (node)." >&2
  exit 2
fi

LOG="$(mktemp /tmp/piano-embedded-production.XXXXXX.log)"
WORK="$(mktemp -d "$ROOT/.piano-embedded-verify.XXXXXX")"
cleanup() {
  if [[ "${PIANO_KEEP_VERIFY_TMP:-0}" != 1 ]]; then
    rm -rf "$WORK"
  fi
}
trap cleanup EXIT
export HOME="$WORK/home"
mkdir -p "$HOME/Music/Piano Teacher"
export PIANO_PYTHON="$PYTHON" GODOT_BIN
export PIANO_TEACHER_PYTHON_HOME="$("$PYTHON" -c 'import sys; print(sys.base_prefix)')"
PY_SITE="$("$PYTHON" -c 'import site; print(site.getsitepackages()[0])')"
PY_LIB="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
export PYTHONPATH="$ROOT:$PY_SITE${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "$PY_LIB" ]]; then
  export LD_LIBRARY_PATH="$PY_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
set_case() {
  local case_name="$1"
  export XDG_CONFIG_HOME="$WORK/config-$case_name"
  export XDG_DATA_HOME="$WORK/data-$case_name"
  export XDG_CACHE_HOME="$WORK/cache-$case_name"
  mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME"
}
check() {
  local label="$1"
  shift
  if "$@" >> "$LOG" 2>&1; then
    printf 'PASS  %s\n' "$label"
  else
    local status=$?
    printf 'FAIL  %s (exit %d)\n' "$label" "$status"
    tail -n 45 "$LOG"
    printf 'Full log: %s\n' "$LOG"
    exit "$status"
  fi
}
seed() {
  "$PYTHON" - "$1" "${2:-}" <<'PY'
import sys
from piano_teacher.library import ScoreLibrary
library = ScoreLibrary()
library.mark_opened(sys.argv[1])
kwargs = {"fullscreen": False}
if sys.argv[2]:
    kwargs["exercise_strategy"] = sys.argv[2]
library.update(**kwargs)
print("SEEDED", sys.argv[1])
PY
}
verify_bridge() {
  set_case bridge
  export PIANO_NATIVE_REAL_SCORE_SMOKE=1
  export PIANO_NATIVE_BRIDGE_TIMEOUT_SECONDS=125
  bash scripts/verify-native-bridge.sh
  unset PIANO_NATIVE_REAL_SCORE_SMOKE
}
make_fixture() {
  "$PYTHON" - <<'PY'
from pathlib import Path
from scripts.smoke_phase0 import make_fixture
target = Path.home() / "Music" / "Piano Teacher" / "phase6_native_fixture.mid"
make_fixture(target)
print("CREATED_FIXTURE", target)
PY
}
verify_fixture_ui() {
  set_case fixture
  seed phase6_native_fixture.mid
  timeout 105s "$GODOT_BIN" --headless --audio-driver Dummy --path godot \
    --script res://production_ui_smoke.gd
}
verify_moonlight() {
  set_case moonlight
  cp midi/Moonlight_Sonata_I.midi "$HOME/Music/Piano Teacher/"
  seed Moonlight_Sonata_I.midi coda-fukuda-midi
  timeout 180s "$GODOT_BIN" --headless --audio-driver Dummy --path godot \
    --script res://production_session_journey.gd
}
verify_real_source() {
  local case_name="$1"
  local score="$2"
  set_case "$case_name"
  cp "midi/$score" "$HOME/Music/Piano Teacher/$score"
  seed "$score" coda-fukuda-midi
  local fingerprint
  fingerprint="$(sha256sum "$HOME/Music/Piano Teacher/$score" | cut -d' ' -f1)"
  timeout 115s "$GODOT_BIN" --headless --audio-driver Dummy --path godot \
    --script res://production_ui_smoke.gd -- "$score" "$fingerprint"
}
audit_package() {
  # The release audit needs a *self-contained* Python prefix. Build one in
  # disposable space from this checkout's exact venv + interpreter; never
  # modify the developer's venv, user settings or existing dist directory.
  local python_version stdlib libpython bundled workspace
  python_version="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  stdlib="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')"
  bundled="$WORK/bundled-python"
  workspace="$WORK/package-worktree"
  libpython="$PY_LIB/libpython$python_version.so"
  if [[ ! -f "$libpython" ]]; then
    echo "Cannot stage libpython: $libpython" >&2
    return 1
  fi
  mkdir -p "$bundled/bin" "$bundled/lib" "$workspace"
  cp -L "$PYTHON" "$bundled/bin/python3"
  cp -L "$libpython" "$bundled/lib/libpython$python_version.so"
  cp -a "$stdlib" "$bundled/lib/python$python_version"
  mkdir -p "$bundled/lib/python$python_version/site-packages"
  cp -a "$PY_SITE/." "$bundled/lib/python$python_version/site-packages/"
  # Copy only tracked source files from the *current working tree* (not a
  # potentially stale git archive), plus generated native build products.
  git ls-files -z | tar -cf - --null -T - | tar -xf - -C "$workspace"
  mkdir -p "$workspace/godot/native/bin"
  cp godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so \
    "$workspace/godot/native/bin/"
  cp godot/native/piano_bridge.gdextension godot/native/python-abi.txt \
    "$workspace/godot/native/"
  (
    cd "$workspace"
    export PIANO_BUNDLED_PYTHON_HOME="$bundled"
    export PIANO_BUNDLED_NODE="$(command -v node)"
    export PIANO_GODOT_BINARY="$GODOT_BIN"
    export PIANO_PACKAGE_AUDIT_ONLY=1
    export PYTHONPATH=""
    timeout 180s bash scripts/package-inprocess.sh
    test -s dist/piano-teacher-linux-x86_64/godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so
    test -x dist/piano-teacher-linux-x86_64/PianoTeacher
  )
}

printf 'Revision: %s\n' "$(git rev-parse --short HEAD)"
printf 'Log: %s\n' "$LOG"
if ! "$PYTHON" scripts/dev_runtime_state.py check-native >> "$LOG" 2>&1; then
  check "Build native bridge for current source/ABI" \
    env PIANO_SKIP_NATIVE_SMOKE=1 bash scripts/build-inprocess.sh
fi
check "Create isolated two-hand MIDI fixture" make_fixture
check "Embedded Godot + Python registration and real score" verify_bridge
check "Production UI / Play / Pause / Resume" verify_fixture_ui
check "Moonlight Sonata / retry / Listen / lesson navigation" verify_moonlight
check "Peace Piece native score" verify_real_source peace \
  'Peace_Piece_-_Bill_Evans_(Piano_Solo).midi'
check "Chopin Nocturne native score" verify_real_source chopin \
  'Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi'
if [[ "$MODE" == full ]]; then
  check "Assembled standalone runtime package audit" audit_package
else
  printf 'SKIP  Package audit (explicit --without-package)\n'
fi
printf 'PASS  LOCAL EMBEDDED PRODUCTION CONTROL\n'
printf 'Full log: %s\n' "$LOG"

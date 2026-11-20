#!/usr/bin/env bash
# Local build, native bridge smoke and package audit of the embedded runtime.
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
FAILED_CASES=()
CASE_COUNT=0
check() {
  local label="$1"
  shift
  CASE_COUNT=$((CASE_COUNT+1))
  local case_log="$WORK/native-case-$CASE_COUNT.log"
  printf '\n=== %s ===\n' "$label" >> "$LOG"
  # Run each existing acceptance case in its own strict Bash process.
  # A failed command inside audit_package must not be accidentally ignored
  # because the parent is evaluating this check in an "if" expression.
  if bash -Eeuo pipefail -c '"$@"' _ "$@" > "$case_log" 2>&1; then
    cat "$case_log" >> "$LOG"
    printf 'PASS  %s\n' "$label"
    return 0
  else
    local status=$?
    cat "$case_log" >> "$LOG"
    printf 'FAIL  %s (exit %d)\n' "$label" "$status"
    tail -n 45 "$case_log"
    FAILED_CASES+=("$label (exit $status)")
    return "$status"
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
import mido

target = Path.home() / "Music" / "Piano Teacher" / "phase6_native_fixture.mid"
target.parent.mkdir(parents=True, exist_ok=True)
piece = mido.MidiFile(type=1, ticks_per_beat=480)
meta = mido.MidiTrack()
piece.tracks.append(meta)
meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
meta.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
meta.append(mido.MetaMessage("end_of_track", time=0))

def add_hand(channel, notes):
    track = mido.MidiTrack()
    piece.tracks.append(track)
    track.append(mido.Message("program_change", channel=channel, program=0, time=0))
    events = []
    for at, pitch, length in notes:
        events.append((at, 1, mido.Message("note_on", channel=channel, note=pitch, velocity=84)))
        events.append((at+length, 0, mido.Message("note_off", channel=channel, note=pitch, velocity=0)))
    last = 0
    for at, _, message in sorted(events, key=lambda item:(item[0],item[1])):
        message.time = at-last
        track.append(message)
        last = at
    track.append(mido.MetaMessage("end_of_track", time=0))

right = [(bar*1920+beat*480, [72,74,76,77,79,77,76,74][(bar+beat)%8], 400)
         for bar in range(8) for beat in range(4)]
left = [(bar*1920+beat*960, [48,55,52,55][(bar+beat)%4], 800)
        for bar in range(8) for beat in range(2)]
add_hand(0,right)
add_hand(1,left)
piece.save(target)
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
  # Preserve both the linker alias and runtime SONAME in the package.
  # A lone .so alias could otherwise hide a dependency on system libpython.
  for python_library in "$PY_LIB"/libpython"$python_version".so*; do
    [[ -f "$python_library" ]] || continue
    cp -L "$python_library" "$bundled/lib/$(basename "$python_library")"
  done
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
    export PYTHONPATH=""
    # Build the actual distributable, then test only its relocated bytes.
    timeout 240s bash scripts/package-inprocess.sh
    test -s dist/piano-teacher-linux-x86_64.tar.gz
  )
  local destination="$WORK/clean-package"
  local clean_home="$WORK/clean-home"
  mkdir -p "$destination" "$clean_home"
  tar -xzf "$workspace/dist/piano-teacher-linux-x86_64.tar.gz" -C "$destination"
  local launcher="$destination/piano-teacher-linux-x86_64/PianoTeacher"
  test -x "$launcher"
  test -s "$destination/piano-teacher-linux-x86_64/godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so"
  # This child inherits neither the builder's venv nor any PYTHONPATH,
  # PIANO_TEACHER_PYTHON_HOME or compiled project import cache.
  local package_log="$WORK/clean-package-boot.log"
  timeout 45s env -i \
    HOME="$clean_home" USER="${USER:-runner}" PATH="/usr/bin:/bin" \
    PIANO_TEACHER_HEADLESS_SMOKE=1 \
    "$launcher" > "$package_log" 2>&1 || {
      tail -n 100 "$package_log" >&2
      return 1
    }
  if ! grep -Fq "PIANO_PACKAGE_NATIVE_READY" "$package_log" || \
       grep -Eq 'Embedded Piano Teacher stopped|SCRIPT ERROR|ERROR:.*(extension|python|libpiano)' "$package_log"; then
    echo "Relocated package did not boot its embedded Python/Godot runtime" >&2
    tail -n 100 "$package_log" >&2
    return 1
  fi
  echo "Relocated standalone package boot passed"
}

# Export only this runner's local case helpers. Each subprocess inherits
# the isolated HOME and native ABI configuration; no case can leave the
# following scenarios unrun after a nonfatal failure.
export ROOT WORK PYTHON GODOT_BIN PY_SITE PY_LIB
export -f set_case seed verify_bridge make_fixture verify_fixture_ui
export -f verify_moonlight verify_real_source audit_package

printf 'Revision: %s\n' "$(git rev-parse --short HEAD)"
printf 'Log: %s\n' "$LOG"
if ! "$PYTHON" scripts/dev_runtime_state.py check-native >> "$LOG" 2>&1; then
  check "Build native bridge for current source/ABI" \
    env PIANO_SKIP_NATIVE_SMOKE=1 bash scripts/build-inprocess.sh || {
      printf 'Native bridge build failed; dependent scenarios cannot run.\n' >&2
      exit 1
    }
fi
check "Create isolated two-hand MIDI fixture" make_fixture || :
check "Embedded Godot + Python registration and real score" verify_bridge || :
check "Production UI / Play / Pause / Resume" verify_fixture_ui || :
check "Moonlight Sonata / retry / Listen / lesson navigation" verify_moonlight || :
check "Peace Piece native score" verify_real_source peace \
  'Peace_Piece_-_Bill_Evans_(Piano_Solo).midi' || :
check "Chopin Nocturne native score" verify_real_source chopin \
  'Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi' || :
if [[ "$MODE" == full ]]; then
  check "Relocated standalone runtime package audit" audit_package || :
else
  printf 'SKIP  Package audit (explicit --without-package)\n'
fi
printf 'Full log: %s\n' "$LOG"
if (("${#FAILED_CASES[@]}" > 0)); then
  printf 'NATIVE ACCEPTANCE FAILED: %d independent scenario(s):\n' "${#FAILED_CASES[@]}" >&2
  printf '  - %s\n' "${FAILED_CASES[@]}" >&2
  exit 1
fi
printf 'PASS  LOCAL EMBEDDED PRODUCTION CONTROL\n'

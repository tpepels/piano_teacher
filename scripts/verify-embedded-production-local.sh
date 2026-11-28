#!/usr/bin/env bash
# Local build, native bridge smoke and package audit of the embedded runtime.
# Run from any directory. All lesson settings and imported MIDI fixtures are
# isolated under a temporary HOME; real learner progress is never modified.
set -Eeuo pipefail
# Optional local-only source for the unresolved Pathétique II regression.
# Resolve before moving to repository root; never commit or package the file.
CALLER_DIR="$PWD"
cd "$(dirname "$0")/.."
ROOT="$PWD"
if [[ -n "${PIANO_PATHETIQUE_II_MIDI:-}" ]]; then
  if [[ "$PIANO_PATHETIQUE_II_MIDI" != /* ]]; then
    PIANO_PATHETIQUE_II_MIDI="$CALLER_DIR/$PIANO_PATHETIQUE_II_MIDI"
  fi
  if [[ ! -f "$PIANO_PATHETIQUE_II_MIDI" ]]; then
    echo "Pathétique II acceptance source not found: $PIANO_PATHETIQUE_II_MIDI" >&2
    exit 2
  fi
  export PIANO_PATHETIQUE_II_MIDI
fi
MODE="${1:-full}"
if [[ "$MODE" != full && "$MODE" != --without-package && "$MODE" != --package-only && "$MODE" != --visual-only ]]; then
  echo "Usage: bash scripts/verify-embedded-production-local.sh [--without-package | --package-only | --visual-only]" >&2
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
if ! "$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3,14); import mido, rtmidi, verovio, cairosvg, PIL, onnxruntime'; then
  echo "Install Python 3.14 packages: .venv/bin/python -m pip install -e '.[godot,test]'" >&2
  exit 2
fi
LOG="$(mktemp "${TMPDIR:-/tmp}/piano-embedded-production.XXXXXX.log")"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/piano-embedded-verify.XXXXXX")"
cleanup() {
  if [[ "${PIANO_KEEP_VERIFY_TMP:-0}" != 1 ]]; then
    rm -rf "$WORK"
  fi
}
trap cleanup EXIT
if [[ "$MODE" == --visual-only ]]; then
  if ! command -v xvfb-run >/dev/null || ! command -v Xvfb >/dev/null || ! command -v xauth >/dev/null; then
    echo "Visual acceptance requires Xvfb, xvfb-run and xauth (plus Mesa OpenGL)." >&2
    exit 2
  fi
  VISUAL_RESULTS="${PIANO_VISUAL_RESULTS:-$HOME/piano-teacher-results/visual-$(date +%Y%m%d-%H%M%S)}"
  mkdir -p "$VISUAL_RESULTS"
  VISUAL_RESULTS="$(realpath "$VISUAL_RESULTS")"
  export VISUAL_RESULTS
fi
sample_bank="${PIANO_TEACHER_SOUNDFONT:-$HOME/.local/share/piano-teacher/soundfonts/salamander-grand-piano.sf2}"
export sample_bank
export HOME="$WORK/home"
mkdir -p "$HOME/Music/Piano Teacher"
PIANO_TEACHER_PYTHON_HOME="$("$PYTHON" -c 'import sys; print(sys.base_prefix)')"
export PIANO_PYTHON="$PYTHON" GODOT_BIN PIANO_TEACHER_PYTHON_HOME
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
  # Every case is bounded and its actual output streams to CI AND the
  # main diagnostic log immediately. The log remains useful even when a
  # native case hangs or the verifier is interrupted before its exit.
  # The underlying Godot/package commands retain their stricter timeouts.
  printf 'RUN   %s\n' "$label"
  if timeout --signal=TERM --kill-after=5s 600s \
      bash -Eeuo pipefail -c '"$@"' _ "$@" 2>&1 | tee -a "$LOG" "$case_log"; then
    # Godot can exit successfully after reporting a GDScript runtime error.
    # Reject that broken player journey instead of counting it as passed.
    if grep -Fq 'SCRIPT ERROR:' "$case_log"; then
      printf 'FAIL  %s (Godot script error)\n' "$label"
      FAILED_CASES+=("$label (Godot script error)")
      return 1
    fi
    if grep -Eq 'ObjectDB instances were leaked|Leaked instance:|TAKE_WITHOUT_SCORE:' "$case_log"; then
      printf 'FAIL  %s (resource leak or lost confirmed score)\n' "$label"
      FAILED_CASES+=("$label (resource leak or lost confirmed score)")
      return 1
    fi
    # Source-queue refusal is a fatal production-journey defect even when
    # Godot keeps its event loop alive and the outer script exits zero.
    # Do not let the physical Pathétique admission failure turn CI green.
    if grep -Eq 'ERROR: (Refused immutable score strip|SCORE_TRANSPORT_(PREFLIGHT|COMMIT):|Queue tail changed|Cannot safely roll back incomplete)' "$case_log"; then
      printf 'FAIL  %s (physical source admission error)\n' "$label"
      FAILED_CASES+=("$label (physical source admission error)")
      return 1
    fi
    printf 'PASS  %s\n' "$label"
    return 0
  else
    local status=$?
    printf 'FAIL  %s (exit %d)\n' "$label" "$status"
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
library.update(fullscreen=False)
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
  "$PYTHON" "$ROOT/scripts/release/make-fixtures.py"
}
run_player() {
  local name="$1" budget="$2"
  shift 2
  if [[ "$MODE" != --visual-only ]]; then
    timeout "$budget" "$GODOT_BIN" --headless --audio-driver Dummy --path godot "$@"
    return
  fi
  local capture="$WORK/visual-$name" output="$VISUAL_RESULTS/$name"
  local status=0
  local required=()
  case "$name" in
    fake-midi-*) required=(--require-step wrong_free --require-step pause_free
      --require-step resume_tempo --require-step second_failure --require-step free_again
      --require-step clean_repeat --require-step hitch_recover --require-step stopped_stable) ;;
    moonlight) required=(--require-step paused --require-step resumed --require-step retry_wait
      --require-step listen_playback --require-step stage_change --require-step reopen) ;;
    fixture) required=(--require-step fixture) ;;
  esac
  mkdir -p "$capture" "$output"
  timeout "$budget" env PIANO_VISUAL_CAPTURE_DIR="$capture" LIBGL_ALWAYS_SOFTWARE=1 \
    xvfb-run -a -s '-screen 0 1600x1000x24' "$GODOT_BIN" \
    --display-driver x11 --rendering-method gl_compatibility --audio-driver Dummy \
    --path godot "$@" || status=$?
  "$PYTHON" "$ROOT/tests/visual_continuity.py" "$capture" "$output" \
    "${required[@]}" || status=1
  if ((status == 0)); then
    rm -rf "$capture"
  else
    echo "Visual failure evidence: $output"
    # Preserve raw capture only on explicit request; report and surrounding
    # images are already outside the disposable test HOME.
    if [[ "${PIANO_KEEP_VISUAL_CAPTURE:-0}" == 1 ]]; then
      mv "$capture" "$output/raw-capture"
    fi
  fi
  return "$status"
}
verify_fixture_ui() {
  set_case fixture
  seed phase6_native_fixture.mid
  run_player fixture 105s --script res://production_ui_smoke.gd
}
verify_score_recovery() {
  set_case score-recovery
  bash scripts/release/verify-score-recovery.sh "$WORK/source-recovery" "$GODOT_BIN" \
    "$ROOT/godot" "$ROOT/tests/godot/score_worker_recovery.gd"
}
verify_fake_midi_ui() {
  # $1: fixture meter, "normal" (4/4) or "two-four" (2/4).
  local variant="${1:-normal}"
  local fixture="ci_state_journey.mid"
  if [[ "$variant" == "two-four" ]]; then
    fixture="ci_state_journey_two_four.mid"
  fi
  set_case "fake-midi-$variant"
  seed "$fixture"
  # Restore the synthetic device as a persisted preference during normal
  # startup discovery. Selecting a new device mid-Listen would correctly
  # interrupt the real passage and invalidate this journey's state graph.
  "$PYTHON" - <<'PY'
from piano_teacher.library import ScoreLibrary
ScoreLibrary().update(midi_device="CI Synthetic Keyboard")
PY
  local port
  port="$("$PYTHON" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
  # sitecustomize exists only on this test's PYTHONPATH. The real embedded
  # engine sees one synthetic mido input and unmodified MIDI callbacks.
  # No production command or fake application path is exposed.
  local scenario_log="$WORK/native-midi-$variant.log"
  # A fresh physical Resume includes an entire authored count-in bar.
  # Bound the longer real-time journey consistently with its Godot budget.
  PIANO_TEST_FAKE_MIDI_PORT="$port" \
    PYTHONPATH="$ROOT/tests/native_fake_midi:$PYTHONPATH" \
    run_player "fake-midi-$variant" 210s --script res://production_fake_midi_journey.gd | tee "$scenario_log"
}
verify_moonlight() {
  set_case moonlight
  cp midi/Moonlight_Sonata_I.midi "$HOME/Music/Piano Teacher/"
  seed Moonlight_Sonata_I.midi
  # Timed Play/Pause/Retry needs a connected piano: the same synthetic
  # keyboard as the fake-MIDI journey (no keys are played here).
  "$PYTHON" - <<'PY'
from piano_teacher.library import ScoreLibrary
ScoreLibrary().update(midi_device="CI Synthetic Keyboard")
PY
  local port
  port="$("$PYTHON" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
  PIANO_TEST_FAKE_MIDI_PORT="$port" \
    PYTHONPATH="$ROOT/tests/native_fake_midi:$PYTHONPATH" \
    run_player moonlight 180s --script res://production_session_journey.gd
}
verify_real_source() {
  local case_name="$1"
  local score="$2"
  local source_path="${3:-midi/$score}"
  set_case "$case_name"
  cp "$source_path" "$HOME/Music/Piano Teacher/$score"
  seed "$score"
  local fingerprint
  fingerprint="$(sha256sum "$HOME/Music/Piano Teacher/$score" | cut -d' ' -f1)"
  timeout 115s "$GODOT_BIN" --headless --verbose --audio-driver Dummy --path godot \
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
  # A distribution's stdlib directory can also contain globally installed
  # packages, including certificate symlinks outside the Python prefix.
  # Stage only the interpreter's stdlib, then the exact application venv.
  mkdir -p "$bundled/lib/python$python_version"
  tar -C "$stdlib" --exclude='./site-packages' -cf - . | \
    tar -C "$bundled/lib/python$python_version" -xf -
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
    export PIANO_GODOT_BINARY="$GODOT_BIN"
    export PYTHONPATH=""
    # Build the actual distributable, then test only its relocated bytes.
    timeout 240s bash scripts/package-inprocess.sh
    test -s dist/piano-teacher-linux-x86_64.tar.gz
  )
  bash "$ROOT/scripts/release/verify-archive.sh" \
    "$workspace/dist/piano-teacher-linux-x86_64.tar.gz" "$sample_bank"
}

# Export only this runner's local case helpers. Each subprocess inherits
# the isolated HOME and native ABI configuration; no case can leave the
# following scenarios unrun after a nonfatal failure.
export ROOT WORK PYTHON GODOT_BIN PY_SITE PY_LIB MODE
export -f set_case seed verify_bridge make_fixture verify_fixture_ui verify_score_recovery run_player
export -f verify_fake_midi_ui verify_moonlight verify_real_source audit_package

printf 'Revision: %s\n' "$(git rev-parse --short HEAD)"
printf 'Log: %s\n' "$LOG"
if ! "$PYTHON" scripts/dev_runtime_state.py check-native >> "$LOG" 2>&1; then
  check "Build native bridge for current source/ABI" \
    env PIANO_SKIP_NATIVE_SMOKE=1 bash scripts/build-inprocess.sh || {
      printf 'Native bridge build failed; dependent scenarios cannot run.\n' >&2
      exit 1
    }
fi
if [[ "$MODE" == --package-only ]]; then
  check "Create isolated two-hand MIDI fixture" make_fixture
  check "Relocated standalone runtime package audit" audit_package
  exit 0
fi
check "Create isolated two-hand MIDI fixture" make_fixture || :
check "Embedded Godot + Python registration and real score" verify_bridge || :
if [[ "$MODE" != --visual-only ]]; then
  check "Native score cancellation, backpressure, crash recovery and restart" verify_score_recovery || :
fi
check "Production UI / Play / Pause / Resume" verify_fixture_ui || :
check "Real Godot practice transitions with synthetic physical MIDI" verify_fake_midi_ui normal || :
check "Same journey in 2/4 (short bars, short rests)" verify_fake_midi_ui two-four || :
check "Moonlight Sonata / retry / Listen / lesson navigation" verify_moonlight || :
if [[ "$MODE" == --visual-only ]]; then
  echo "Visual results: $VISUAL_RESULTS"
  if (( ${#FAILED_CASES[@]} > 0 )); then
    printf "FAIL  VISUAL CONTINUITY: %s\n" "${FAILED_CASES[@]}" >&2
    exit 1
  fi
  echo "PASS  RENDERED VISUAL CONTINUITY"
  exit 0
fi
# Every checked-in MIDI source is part of the real native acceptance
# corpus. Do not quietly narrow the scope to a few handpicked pieces:
# source-specific ties, meters, multipage layouts, long rests and
# release tails can break admission even when a small fixture passes.
# Moonlight is exercised separately by its deeper lesson-navigation
# journey above, so do not rerun it with the generic UI workflow.
CORPUS_CHECKED=0
CORPUS_CASE=0
while IFS= read -r -d '' midi_file; do
  score="${midi_file#midi/}"
  [[ "$score" == "Moonlight_Sonata_I.midi" ]] && continue
  CORPUS_CASE=$((CORPUS_CASE+1))
  check "Native repertoire ${CORPUS_CASE}: ${score}" \
    verify_real_source "corpus-${CORPUS_CASE}" "$score" || :
  CORPUS_CHECKED=$((CORPUS_CHECKED+1))
done < <(find midi -maxdepth 1 -type f -name '*.midi' -print0 | sort -z)
if ((CORPUS_CHECKED == 0)); then
  echo "FAIL  Native repertoire corpus is empty" >&2
  FAILED_CASES+=("Native repertoire corpus is empty")
fi
printf 'NATIVE_REPERTOIRE_CORPUS_CHECKED=%d\n' "$CORPUS_CHECKED"
if [[ -n "${PIANO_PATHETIQUE_II_MIDI:-}" ]]; then
  # The real source is not bundled with the repository. Run the same
  # embedded Godot/Verovio/physical-reservation journey as every corpus
  # item, against an isolated copy in a disposable test HOME.
  check "Native Pathétique II externally supplied MIDI" verify_real_source \
    "pathétique-II" "external_pathetique_II.midi" "$PIANO_PATHETIQUE_II_MIDI" || :
  printf 'NATIVE_PATHETIQUE_II_SOURCE_CHECKED=1\n'
else
  printf 'PENDING NATIVE_PATHETIQUE_II_SOURCE: supply PIANO_PATHETIQUE_II_MIDI to verify the original regression\n'
fi
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

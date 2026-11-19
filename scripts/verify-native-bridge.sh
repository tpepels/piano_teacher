#!/usr/bin/env bash
# Validate the actual Godot loader + embedded CPython library endpoint.
# Safe on the developer machine: no listeners, sockets or service startup.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
GODOT_BIN="${GODOT_BIN:-$(command -v godot || command -v godot4 || true)}"
if [[ -z "$GODOT_BIN" || ! -x "$GODOT_BIN" ]]; then
  echo "A Godot 4.7 executable is required for native startup verification" >&2
  exit 1
fi
test -s godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so || {
  echo "Native library not built" >&2; exit 1;
}
test -s godot/native/piano_bridge.gdextension || {
  echo "Native .gdextension manifest missing" >&2; exit 1;
}
# A GDExtension linked against CPython must see exactly the interpreter and
# venv packages used by Piano Teacher, including when the build calls us.
PYTHON="${PIANO_PYTHON:-$PWD/.venv/bin/python}"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
PY_SITE="$("$PYTHON" -c 'import site; print(site.getsitepackages()[0])')"
PY_BASE="$("$PYTHON" -c 'import sys; print(sys.base_prefix)')"
PY_LIB="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
export PIANO_TEACHER_PYTHON_HOME="$PY_BASE"
export PYTHONPATH="$PWD:$PY_SITE${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "$PY_LIB" ]]; then
  export LD_LIBRARY_PATH="$PY_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
echo "Importing native extension into the Godot project ..."
timeout 35s "$GODOT_BIN" --headless --path godot --editor --import
echo "Checking extension registration, embedded Python and library.catalog ..."
bridge_log="$(mktemp -t piano-native-bridge.XXXXXX)"
trap 'rm -f "$bridge_log"' EXIT
timeout "${PIANO_NATIVE_BRIDGE_TIMEOUT_SECONDS:-18}s" "$GODOT_BIN" --headless --path godot \
  --script res://native_bridge_smoke.gd 2>&1 | tee "$bridge_log"
# Godot can return process exit 0 after SceneTree.quit(1) during headless
# shutdown. The acceptance marker and explicit failure line are both
# checked; a hidden failed practice transport can no longer pass startup.
if grep -Fq "PIANO_NATIVE_STARTUP_FAILED:" "$bridge_log"; then
  echo "Native startup smoke reported a failure" >&2
  exit 1
fi
if [[ "${PIANO_NATIVE_REAL_SCORE_SMOKE:-0}" == "1" ]]; then
  grep -Fq "PIANO_NATIVE_REAL_SCORE_WORKFLOW_OK" "$bridge_log" || {
    echo "Native real-score transport did not complete" >&2; exit 1;
  }
else
  grep -Fq "PIANO_NATIVE_LIBRARY_OK" "$bridge_log" || {
    echo "Native library startup did not complete" >&2; exit 1;
  }
fi

# This marker is valid only until the binary or manifest changes.
mkdir -p godot/.godot
touch godot/.godot/piano-native-verified

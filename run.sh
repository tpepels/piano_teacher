#!/usr/bin/env bash
# Developer launcher: verify the exact embedded runtime before showing the UI.
set -Eeuo pipefail
cd "$(dirname "$0")"
GODOT="$(command -v godot || command -v godot4 || true)"
test -n "$GODOT" || { echo "Godot 4.7.2 is required" >&2; exit 1; }
PYTHON="$PWD/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
export PIANO_PYTHON="$PYTHON"

# Rebuild native code only if native sources, ABI, or binary changed. On a new
# checkout without a build fingerprint, perform one safe rebuild.
if ! "$PYTHON" scripts/dev_runtime_state.py check-native; then
    echo "Native bridge is missing or stale; rebuilding for this checkout..." >&2
    if ! bash scripts/build-inprocess.sh; then
        echo "Automatic native build failed. Install SCons/native dependencies or" >&2
        echo "install a matching precompiled extension artifact." >&2
        exit 1
    fi
    "$PYTHON" scripts/dev_runtime_state.py check-native || {
        echo "New native bridge failed the source/ABI integrity check." >&2
        exit 1
    }
fi

PY_SITE="$("$PYTHON" -c 'import site; print(site.getsitepackages()[0])')"
PY_BASE="$("$PYTHON" -c 'import sys; print(sys.base_prefix)')"
PY_LIB="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
if [[ -n "$PY_LIB" ]]; then
    export LD_LIBRARY_PATH="$PY_LIB:$(printenv LD_LIBRARY_PATH || true)"
fi
export PIANO_TEACHER_PYTHON_HOME="$PY_BASE"
export PYTHONPATH="$PWD:$PY_SITE:$(printenv PYTHONPATH || true)"

# Changes to Python, Godot, packages, the binary or editor invalidate the
# startup smoke. A passing old smoke must never hide a broken source pull.
stamp=godot/.godot/piano-native-runtime-sha256
signature="$("$PYTHON" scripts/dev_runtime_state.py runtime-signature --godot "$GODOT")" || exit 1
if [[ ! -f "$stamp" || "$(cat "$stamp")" != "$signature" ]]; then
    echo "Runtime changed: verifying Godot registration and embedded Python..." >&2
    rm -f "$stamp"
    if ! GODOT_BIN="$GODOT" bash scripts/verify-native-bridge.sh; then
        echo "Runtime verification failed. The application was not launched." >&2
        exit 1
    fi
    signature="$("$PYTHON" scripts/dev_runtime_state.py runtime-signature --godot "$GODOT")"
    mkdir -p "$(dirname "$stamp")"
    tmp="$(mktemp "$(dirname "$stamp")/.runtime-verified.XXXXXX")"
    printf '%s\n' "$signature" > "$tmp"
    mv -f "$tmp" "$stamp"
fi
exec "$GODOT" --path godot -- "$@"

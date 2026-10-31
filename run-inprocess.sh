#!/usr/bin/env bash
# Native proof-of-integration launcher. Does not start a server or bind ports.
set -Eeuo pipefail
cd "$(dirname "$0")"
if [[ ! -s godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so ||
      ! -f godot/native/piano_bridge.gdextension ]]; then
  echo "Missing the precompiled in-process extension." >&2
  echo "Download the piano-native-linux-x86_64-py314 artifact from the" >&2
  echo "Embedded Python bridge GitHub Actions run for this commit, then:" >&2
  echo "  python3 scripts/install-inprocess-artifact.py /path/to/artifact.zip" >&2
  echo "Developer-only alternative: bash scripts/build-inprocess.sh" >&2
  exit 1
fi
GODOT="$(command -v godot || command -v godot4 || true)"
test -n "$GODOT" || { echo "Godot is needed during development" >&2; exit 1; }
# Editable/dev environment only. A published bundle sets these paths to its
# vendored CPython runtime and installs no dependencies on the user's OS.
PYTHON="$PWD/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
PY_SITE="$("$PYTHON" -c 'import site; print(site.getsitepackages()[0])')"
PY_BASE="$("$PYTHON" -c 'import sys; print(sys.base_prefix)')"
PY_ABI="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ -f godot/native/python-abi.txt && "$(cat godot/native/python-abi.txt)" != "$PY_ABI" ]]; then
  echo "This native extension needs CPython $(cat godot/native/python-abi.txt), but your venv uses $PY_ABI." >&2
  exit 1
fi
PY_LIB="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
if [[ -n "$PY_LIB" ]]; then
  export LD_LIBRARY_PATH="$PY_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
export PIANO_TEACHER_PYTHON_HOME="$PY_BASE"
export PYTHONPATH="$PWD:$PY_SITE${PYTHONPATH:+:$PYTHONPATH}"
exec "$GODOT" --path godot -- --in-process "$@"

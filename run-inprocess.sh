#!/usr/bin/env bash
# Native proof-of-integration launcher. Does not start a server or bind ports.
set -Eeuo pipefail
cd "$(dirname "$0")"
if [[ ! -s godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so ||
      ! -f godot/native/piano_bridge.gdextension ]]; then
  echo "Build the in-process extension first: bash scripts/build-inprocess.sh" >&2
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
export PIANO_TEACHER_PYTHON_HOME="$PY_BASE"
export PYTHONPATH="$PWD:$PY_SITE${PYTHONPATH:+:$PYTHONPATH}"
exec "$GODOT" --path godot -- --in-process "$@"

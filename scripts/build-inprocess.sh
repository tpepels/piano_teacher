#!/usr/bin/env bash
# Developer build only. The distributed application contains the result.
# Never build godot-cpp or pip-install packages on the user's machine.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
GODOT_CPP_VERSION=10.0.0-stable
# This script is for CI and contributors only. The application runs with the
# downloaded/bundled binary and never invokes a compiler or SCons.
if ! command -v scons >/dev/null 2>&1; then
  echo "Local compilation needs SCons. For a no-build install, download the" >&2
  echo "piano-native-linux-x86_64-py314 artifact from GitHub Actions and run:" >&2
  echo "  python3 scripts/install-inprocess-artifact.py /path/to/artifact.zip" >&2
  echo "Or install SCons in the project venv to compile locally:" >&2
  echo "  .venv/bin/python -m pip install scons" >&2
  exit 1
fi
if [[ ! -f native/godot-cpp/SConstruct ]]; then
  git clone --depth 1 --branch "$GODOT_CPP_VERSION" \
    https://github.com/godotengine/godot-cpp.git native/godot-cpp
fi
if [[ -z "${PIANO_PYTHON:-}" ]]; then
  PIANO_PYTHON="$PWD/.venv/bin/python"
  if [[ ! -x "$PIANO_PYTHON" ]]; then
    PIANO_PYTHON=python3
  fi
fi
PYTHON_VERSION="$("$PIANO_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "Building with CPython ABI $PYTHON_VERSION"
export PATH="$(dirname "$(command -v "$PIANO_PYTHON")"):$PATH"
(
  cd native
  scons platform=linux target=template_release -j2
)
test -s godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so
cp native/piano_bridge.gdextension.in godot/native/piano_bridge.gdextension
printf '%s\n' "$PYTHON_VERSION" > godot/native/python-abi.txt
echo "Built Godot/CPython extension. Now run: ./run-inprocess.sh"

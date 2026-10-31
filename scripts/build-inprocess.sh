#!/usr/bin/env bash
# Developer build only. The distributed application contains the result.
# Never build godot-cpp or pip-install packages on the user's machine.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
GODOT_CPP_VERSION=10.0.0-stable
if ! command -v scons >/dev/null; then
  echo "Build prerequisite missing: scons (runtime users do not need it)" >&2
  exit 1
fi
if [[ ! -f native/godot-cpp/SConstruct ]]; then
  git clone --depth 1 --branch "$GODOT_CPP_VERSION" \
    https://github.com/godotengine/godot-cpp.git native/godot-cpp
fi
: "${PIANO_PYTHON:=python3}"
PYTHON_VERSION="$("$PIANO_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "Building with CPython ABI $PYTHON_VERSION"
export PATH="$(dirname "$(command -v "$PIANO_PYTHON")"):$PATH"
(
  cd native
  scons platform=linux target=template_release -j2
)
test -s godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so
cp native/piano_bridge.gdextension.in godot/native/piano_bridge.gdextension
echo "Built Godot/CPython extension. Now run: ./run-inprocess.sh"

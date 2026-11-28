#!/usr/bin/env bash
# Developer/release-builder tool. Its output runs without pip, git, a Python
# install, a Godot install, or any TCP/UDP server. Native device/graphics
# drivers and the Linux kernel are necessarily supplied by the host.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
: "${PIANO_BUNDLED_PYTHON_HOME:?Set to a self-contained Python prefix with required wheels installed}"
: "${PIANO_GODOT_BINARY:?Set to a compatible Godot 4.7 x86_64 executable}"
test -x "$PIANO_BUNDLED_PYTHON_HOME/bin/python3"
test -x "$PIANO_GODOT_BINARY"
test -s godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so
test -f godot/native/piano_bridge.gdextension
PY="$PIANO_BUNDLED_PYTHON_HOME/bin/python3"
PY_VERSION="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_LIB_DIR="$PIANO_BUNDLED_PYTHON_HOME/lib"
test -e "$PY_LIB_DIR/libpython$PY_VERSION.so" || {
  echo "Bundled CPython must contain a shared libpython$PY_VERSION.so" >&2
  exit 1
}
"$PY" -c 'import mido, rtmidi, verovio, cairosvg, PIL, onnxruntime'
STAGE="$PWD/dist/piano-teacher-linux-x86_64"
rm -rf "$STAGE"
mkdir -p "$STAGE/bin" "$STAGE/licenses"
PYTHONDONTWRITEBYTECODE=1 "$PY" scripts/release/stage.py "$STAGE"
install -m 644 scripts/release/Verovio-fonts.txt scripts/release/godot-cpp-LICENSE.md "$STAGE/licenses/"
cp "$PIANO_GODOT_BINARY" "$STAGE/bin/godot"
cat > "$STAGE/PianoTeacher" <<'LAUNCH'
#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export PIANO_TEACHER_PYTHON_HOME="$HERE/runtime/python"
export PIANO_PYTHON="$HERE/runtime/python/bin/python3"
export PYTHONHOME="$HERE/runtime/python"
export LD_LIBRARY_PATH="$HERE/runtime/python/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
PY_VER="$("$HERE/runtime/python/bin/python3" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
export PYTHONPATH="$HERE:$HERE/runtime/python/lib/python$PY_VER/site-packages"
export PATH="$HERE/bin:$PATH"
export PYTHONNOUSERSITE=1
# CI verifies the installed *package*, from a relocated clean extraction.
# This opt-in mode never touches normal desktop startup or the score clock.
if [[ "${PIANO_TEACHER_HEADLESS_SMOKE:-0}" == "1" ]]; then
  exec "$HERE/bin/godot" --headless --audio-driver Dummy --max-fps 60 --quit-after 1800 \
    --path "$HERE/godot" -- --in-process
fi
exec "$HERE/bin/godot" --path "$HERE/godot" -- --in-process "$@"
LAUNCH
chmod +x "$STAGE/PianoTeacher"
# The released folder cannot rely on the editor's first-launch importer.
# Compile real Ogg/assets into the staged project with the bundled Godot
# editor in CI, then preserve ONLY its required imported runtime bytes.
# The editor cache itself, development scripts and test sources stay out.
env PYTHONDONTWRITEBYTECODE=1 PYTHONHOME="$STAGE/runtime/python" \
  PYTHONPATH="$STAGE:$STAGE/runtime/python/lib/python$PY_VERSION/site-packages" \
  LD_LIBRARY_PATH="$STAGE/runtime/python/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  timeout 90s "$STAGE/bin/godot" --headless --editor --import --path "$STAGE/godot"
test -d "$STAGE/godot/.godot/imported"
"$STAGE/bin/godot" --headless --path "$STAGE/godot" --script "$PWD/scripts/release/godot_licenses.gd" \
  -- "$STAGE/licenses/Godot.txt"
for name in ichi ni san shi; do
  test -s "$STAGE/godot/assets/countin/$name.ogg"
  test -s "$STAGE/godot/assets/countin/$name.ogg.import"
  imported_path="$(sed -n 's/^path="res:\/\/\(.\+\)"$/\1/p' "$STAGE/godot/assets/countin/$name.ogg.import" | head -n 1)"
  test -n "$imported_path"
  test -s "$STAGE/godot/$imported_path" || {
    echo "Missing prepared native count-in audio: $name ($imported_path)" >&2
    exit 1
  }
done
find "$STAGE/godot/.godot" -mindepth 1 -maxdepth 1 \
  ! -name imported -exec rm -rf {} +
find "$STAGE" -name __pycache__ -type d -prune -exec rm -rf {} +
# Verify that the runtime's independently built import bytes are included.
python3 scripts/verify-package-contents.py --root "$STAGE" --package
# Validate imports through the assembled prefix, not the builder environment.
env PYTHONDONTWRITEBYTECODE=1 PYTHONHOME="$STAGE/runtime/python" \
  PYTHONPATH="$STAGE:$STAGE/runtime/python/lib/python$PY_VERSION/site-packages" \
  LD_LIBRARY_PATH="$STAGE/runtime/python/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$STAGE/runtime/python/bin/python3" -P - <<'PY'
import piano_teacher, music21, mido, rtmidi, verovio, cairosvg, PIL, onnxruntime
from piano_teacher.fingering.model_assets import ONNX_RUNTIME_VERSION

if onnxruntime.__version__ != ONNX_RUNTIME_VERSION:
    raise SystemExit(f"Expected ONNX Runtime {ONNX_RUNTIME_VERSION}, found {onnxruntime.__version__}")
if "CPUExecutionProvider" not in onnxruntime.get_available_providers():
    raise SystemExit("Bundled ONNX Runtime must provide the CPU execution provider")
PY
python3 scripts/release/inventory.py "$STAGE" > dist/runtime-inventory.json
# Phase 5 gates the assembled real runtime. Creating and clean-machine
# executing the compressed distributable is a separate Phase 7 release gate.
if [[ "${PIANO_PACKAGE_AUDIT_ONLY:-0}" == "1" ]]; then
  echo "Assembled standalone runtime import/assets audit passed"
  exit 0
fi
tar -C dist -czf dist/piano-teacher-linux-x86_64.tar.gz piano-teacher-linux-x86_64
du -sb "$STAGE" dist/piano-teacher-linux-x86_64.tar.gz
echo "Package: dist/piano-teacher-linux-x86_64.tar.gz (inventory: dist/runtime-inventory.json)"

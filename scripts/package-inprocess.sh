#!/usr/bin/env bash
# Developer/release-builder tool. Its output runs without pip, git, a Python
# install, a Godot install, or any TCP/UDP server. Native device/graphics
# drivers and the Linux kernel are necessarily supplied by the host.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
: "${PIANO_BUNDLED_PYTHON_HOME:?Set to a self-contained Python prefix with required wheels installed}"
: "${PIANO_GODOT_BINARY:?Set to a compatible Godot 4.7 x86_64 executable}"
: "${PIANO_BUNDLED_NODE:?Set to a bundled Node 20+ executable for fingering}"
test -x "$PIANO_BUNDLED_PYTHON_HOME/bin/python3"
test -x "$PIANO_GODOT_BINARY"
test -x "$PIANO_BUNDLED_NODE"
test -s godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so
test -f godot/native/piano_bridge.gdextension
PY="$PIANO_BUNDLED_PYTHON_HOME/bin/python3"
PY_VERSION="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_LIB_DIR="$PIANO_BUNDLED_PYTHON_HOME/lib"
test -e "$PY_LIB_DIR/libpython$PY_VERSION.so" || {
  echo "Bundled CPython must contain a shared libpython$PY_VERSION.so" >&2
  exit 1
}
"$PY" -c 'import mido, rtmidi, verovio, music21, cairosvg, PIL'
STAGE="$PWD/dist/piano-teacher-linux-x86_64"
rm -rf "$STAGE"
mkdir -p "$STAGE/runtime" "$STAGE/bin"
cp -a godot "$STAGE/godot"
cp -a piano_teacher "$STAGE/piano_teacher"
cp -a midi "$STAGE/midi" 2>/dev/null || true
cp -a "$PIANO_BUNDLED_PYTHON_HOME" "$STAGE/runtime/python"
cp "$PIANO_GODOT_BINARY" "$STAGE/bin/godot"
cp "$PIANO_BUNDLED_NODE" "$STAGE/bin/node"
find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +
cat > "$STAGE/PianoTeacher" <<'LAUNCH'
#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export PIANO_TEACHER_PYTHON_HOME="$HERE/runtime/python"
export LD_LIBRARY_PATH="$HERE/runtime/python/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
PY_VER="$("$HERE/runtime/python/bin/python3" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
export PYTHONPATH="$HERE:$HERE/runtime/python/lib/python$PY_VER/site-packages"
export PATH="$HERE/bin:$PATH"
exec "$HERE/bin/godot" --path "$HERE/godot" -- --in-process "$@"
LAUNCH
chmod +x "$STAGE/PianoTeacher"
# Distribution must not contain project development plugins that open
# localhost services. Keep the application runtime independent of MCP.
python3 - "$STAGE/godot/project.godot" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
s = s.replace('[autoload]\n\nMCPRuntimeServer="*res://addons/godot_mcp_toolkit/runtime/mcp_runtime_server.gd"\n\n', '')
s = s.replace('[editor_plugins]\n\nenabled=PackedStringArray("res://addons/godot_mcp_toolkit/plugin.cfg")\n\n', '')
p.write_text(s)
PY
rm -rf "$STAGE/godot/addons/godot_mcp_toolkit"
tar -C dist -czf dist/piano-teacher-linux-x86_64.tar.gz piano-teacher-linux-x86_64
echo "Package: dist/piano-teacher-linux-x86_64.tar.gz"

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if command -v godot >/dev/null 2>&1; then
  GODOT=godot
elif command -v godot4 >/dev/null 2>&1; then
  GODOT=godot4
else
  echo "Godot 4 is required. On Arch: sudo pacman -S godot" >&2
  exit 1
fi
# Validate GDScript before launching the fullscreen window. Python unit tests
# cannot catch parse errors, which otherwise appear as an empty grey screen.
PARSER_OUTPUT=""
if ! PARSER_OUTPUT="$("$GODOT" --headless --path godot --check-only --script res://main.gd 2>&1)"; then
  printf '%s\n' "$PARSER_OUTPUT" >&2
  echo "Godot cannot parse the Piano Teacher interface. See the script error above." >&2
  exit 1
fi
if [[ "$PARSER_OUTPUT" == *"SCRIPT ERROR"* || "$PARSER_OUTPUT" == *"Parse Error:"* ]]; then
  printf '%s\n' "$PARSER_OUTPUT" >&2
  echo "Godot reported a script parse error. The application was not launched." >&2
  exit 1
fi
# A few Python/Arch editable-install combinations omit the project from sys.path.
# Explicitly select this checkout and its venv; do not start a disconnected GUI.
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="$PWD/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python)"
fi
if ! "$PYTHON" -c 'import piano_teacher.server' >/dev/null; then
  echo "Cannot import piano_teacher. Run: source .venv/bin/activate && pip install -e '.[godot,test]'" >&2
  exit 1
fi
"$PYTHON" -m piano_teacher.server &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT
# Fail visibly if the Python backend exits before Godot connects.
BACKEND_READY=0
for _ in $(seq 1 150); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Piano Teacher backend exited during startup." >&2
    wait "$BACKEND_PID" || true
    exit 1
  fi
  if "$PYTHON" -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8765/state", timeout=0.2)' >/dev/null 2>&1; then
    BACKEND_READY=1
    break
  fi
  sleep 0.1
done
if [[ "$BACKEND_READY" -ne 1 ]]; then
  echo "The Python backend did not become ready on 127.0.0.1:8765" >&2
  exit 1
fi
"$GODOT" --path godot

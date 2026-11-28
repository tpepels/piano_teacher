#!/usr/bin/env bash
# Verify exported bytes with no builder interpreter or application sources.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
archive="$(realpath "${1:?pass the desktop archive}")"
sample_bank="${2:-}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
verify_archive() {
  local destination="$WORK/clean-package"
  local clean_home="$WORK/clean-home"
  mkdir -p "$destination" "$clean_home"
  tar -xzf "$archive" -C "$destination"
  local launcher="$destination/piano-teacher-linux-x86_64/PianoTeacher"
  test -x "$launcher"
  test -s "$destination/piano-teacher-linux-x86_64/godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so"
  # This child inherits neither the builder's venv nor any PYTHONPATH,
  # PIANO_TEACHER_PYTHON_HOME or compiled project import cache.
  local package_log="$WORK/clean-package-boot.log"
  local package_tools="$WORK/package-tools"
  local fixture="$clean_home/Music/Piano Teacher/phase6_native_fixture.mid"
  mkdir -p "$(dirname "$fixture")" "$package_tools"
  # Only the launcher utilities are on PATH. There is no host Node or Python.
  ln -s "$(command -v bash)" "$(command -v dirname)" "$package_tools"
  local release="${launcher%/*}"
  local -a packaged=(env -i HOME="$clean_home" PATH="$package_tools"
    PIANO_PYTHON="$release/runtime/python/bin/python3" PYTHONNOUSERSITE=1
    PIANO_TEACHER_PYTHON_HOME="$release/runtime/python" PYTHONHOME="$release/runtime/python"
    LD_LIBRARY_PATH="$release/runtime/python/lib" PYTHONPATH="$release")
  test ! -e "$release/bin/node"
  "${packaged[@]}" "$release/runtime/python/bin/python3" -P "$ROOT/scripts/release/make-fixtures.py"
  "${packaged[@]}" "$release/runtime/python/bin/python3" -P - "$clean_home" "$fixture" <<'PY'
from pathlib import Path
import sys
from piano_teacher.library import ScoreLibrary
home, fixture = map(Path, sys.argv[1:])
library = ScoreLibrary(config_dir=home / '.config/piano-teacher')
library.update(music_dir=str(fixture.parent), fullscreen=False)
library.mark_opened(fixture.name)
PY
  timeout 45s env -i \
    HOME="$clean_home" USER="${USER:-runner}" PATH="$package_tools" \
    PIANO_TEACHER_HEADLESS_SMOKE=1 PIANO_TEACHER_TIMING_DIAGNOSTICS=1 \
    "$launcher" > "$package_log" 2>&1 || {
      tail -n 100 "$package_log" >&2
      return 1
    }
  if ! grep -Fq "PIANO_PACKAGE_NATIVE_READY" "$package_log" || \
       ! grep -Eq 'SCORE_WORKER_GENERATION: [0-9]+ score\.bundle ' "$package_log" || \
       ! grep -Fq "NATIVE_MODEL_READY:" "$package_log" || \
       grep -Eq 'Embedded Piano Teacher stopped|SCRIPT ERROR|ERROR:.*(extension|python|libpiano)' "$package_log"; then
    echo "Relocated package did not generate and install its native score" >&2
    tail -n 100 "$package_log" >&2
    return 1
  fi
  "${packaged[@]}" "$release/runtime/python/bin/python3" -P - "$clean_home" <<'PY'
import json
from pathlib import Path
import sys

cache = Path(sys.argv[1]) / ".local/share/piano-teacher/fingering"
plans = [json.loads(file.read_text()) for file in cache.glob("*/plan-*.json")]
assert len(plans) == 1, "Relocated package did not save the new score's fingering plan"
plan = plans[0]
assert plan["provider"]["runtime"] == "onnxruntime@1.30.0/cpu", plan["provider"]
assert {note["hand"] for note in plan["assignments"].values()
        if note["finger"] is not None} == {"left", "right"}, plan["status"]
PY
  "${packaged[@]}" "$release/runtime/python/bin/python3" -P "$ROOT/scripts/release/verify-relocated.py" "$WORK"
  if [[ -f "$sample_bank" ]]; then
    "${packaged[@]}" PIANO_TEACHER_SOUNDFONT="$sample_bank" \
      "$release/runtime/python/bin/python3" -P "$ROOT/scripts/release/verify-relocated.py" "$WORK"
  fi
  ln -s "$(command -v sleep)" "$(command -v timeout)" "$(command -v mkdir)" "$(command -v cat)" \
    "$(command -v chmod)" "$(command -v env)" "$package_tools"
  # Carry the existing recovery journey outside the installed project.
  "${packaged[@]}" bash "$ROOT/scripts/release/verify-score-recovery.sh" "$WORK/package-recovery" \
    "$release/bin/godot" "$release/godot" "$ROOT/tests/godot/score_worker_recovery.gd" \
    2>&1 | tee "$WORK/recovery.log"
  grep -Eq '^NATIVE_SCORE_RECOVERY_FAILURES:[[:space:]]*0$' "$WORK/recovery.log"
  if grep -Fq 'SCRIPT ERROR:' "$WORK/recovery.log"; then
    return 1
  fi
  echo "Relocated standalone package generated both hands' fingerings and native notation"
}
verify_archive

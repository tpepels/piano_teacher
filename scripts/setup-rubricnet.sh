#!/usr/bin/env bash
# One-time optional RubricNet research extractor installation. The app works
# without this environment; the trained strategy deliberately fails without it.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
TARGET="$PWD/.rubricnet-venv"
if command -v uv >/dev/null 2>&1; then
  uv venv --python 3.12 "$TARGET"
  PY="$TARGET/bin/python"
  uv pip install --python "$PY" --index-url https://download.pytorch.org/whl/cpu 'torch==2.5.1+cpu'
  uv pip install --python "$PY" \
    'music21>=9.1,<10' numpy scipy pandas scikit-learn \
    sortedcontainers lxml matplotlib seaborn
else
  command -v python3.12 >/dev/null 2>&1 || {
    echo "Install uv or Python 3.12 for the isolated RubricNet worker" >&2
    exit 1
  }
  python3.12 -m venv "$TARGET"
  PY="$TARGET/bin/python"
  "$PY" -m pip install 'torch==2.5.1+cpu' \
    --index-url https://download.pytorch.org/whl/cpu
  "$PY" -m pip install 'music21>=9.1,<10' numpy scipy pandas \
    scikit-learn sortedcontainers lxml matplotlib seaborn
fi
"$PY" -c 'import music21, torch, scipy, sklearn, pandas, sortedcontainers; print("RubricNet worker ready (offline after setup)")'
printf 'PIANO_TEACHER_RUBRICNET_PYTHON=%s\n' "$PY"

"""Shared test support.

The LumiKey fingering runtime (Node + ONNX) is an optional, separately
installed component: ``scripts/setup-fingering.sh`` fills the git-ignored
``piano_teacher/fingering/lumikey_runtime/node_modules``. Without it the
product reports an explicit ``unavailable`` fingering plan (and tests of that
behaviour still run); tests that need real predictions depend on the
``lumikey_runtime`` fixture, which skips them with the precise reason.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from piano_teacher.fingering.lumikey import RUNTIME

_PROBE = {"notes": [{"source_id": "probe", "left": False, "note": 60, "time": 0, "duration": 500}]}
_unavailable: str | None = None
_probed = False


def _probe_lumikey_runtime() -> str | None:
    """Return why the real runtime cannot predict, or None if it works.

    Runs the real bridge once on one note, offline, exactly as production does.
    """
    node = os.environ.get("PIANO_FINGERING_NODE", "node")
    try:
        run = subprocess.run([node, str(RUNTIME / "bridge.cjs")], input=json.dumps(_PROBE),
                             capture_output=True, text=True, timeout=120, check=False,
                             env={**os.environ, "OMP_NUM_THREADS": "1"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"LumiKey fingering runtime cannot start ({exc})"
    if run.returncode:
        lines = [line.strip() for line in run.stderr.splitlines() if line.strip()]
        detail = next((line for line in lines if line.startswith("Error")), None) or (
            lines[0] if lines else "no error output")
        return f"LumiKey fingering runtime is not installed or broken ({detail})"
    return None


@pytest.fixture(scope="session")
def lumikey_runtime():
    global _unavailable, _probed
    if not _probed:
        _unavailable, _probed = _probe_lumikey_runtime(), True
    if _unavailable:
        pytest.skip(f"{_unavailable}; run scripts/setup-fingering.sh")

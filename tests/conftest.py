"""Shared test support.

The LumiKey fingering runtime (Node + ONNX) is an optional, separately
installed component: ``scripts/setup-fingering.sh`` fills the git-ignored
``piano_teacher/fingering/lumikey_runtime/node_modules``. Without it the
product reports an explicit ``unavailable`` fingering plan (and tests of that
behaviour still run); tests that need real predictions depend on the
``lumikey_runtime`` fixture, which skips them with the precise reason.
"""
from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess

import pytest

from piano_teacher.fingering.lumikey import RUNTIME
from quarantine_plugin import pytest_collection_modifyitems  # noqa: F401  (tests/quarantine.txt hook)

_PROBE = {"notes": [{"source_id": "probe", "left": False, "note": 60, "time": 0, "duration": 500}]}


@functools.cache
def _probe_lumikey_runtime() -> tuple[str, str]:
    """Classify the real runtime: ("ok"|"absent"|"broken", detail).

    Runs the real bridge once on one note, offline, exactly as production does.
    Only genuine absence (no node binary, no node_modules, MODULE_NOT_FOUND)
    is "absent" and skips; every other failure is "broken" and must fail.
    """
    node = os.environ.get("PIANO_FINGERING_NODE", "node")
    if shutil.which(node) is None:
        return "absent", f"node binary {node!r} not found"
    if not (RUNTIME / "node_modules").is_dir():
        return "absent", f"{RUNTIME / 'node_modules'} is missing"
    try:
        run = subprocess.run([node, str(RUNTIME / "bridge.cjs")], input=json.dumps(_PROBE),
                             capture_output=True, text=True, timeout=120, check=False,
                             env={**os.environ, "OMP_NUM_THREADS": "1"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "broken", f"cannot run or hung: {exc!r}"
    if run.returncode == 0:
        return "ok", ""
    if "MODULE_NOT_FOUND" in run.stderr or "Cannot find module" in run.stderr:
        lines = [x.strip() for x in run.stderr.splitlines() if x.strip()]
        return "absent", next((x for x in lines if x.startswith("Error")), lines[0] if lines else "module not found")
    return "broken", f"exit {run.returncode}: {run.stderr[-2000:]}"


@pytest.fixture(scope="session")
def lumikey_runtime():
    state, detail = _probe_lumikey_runtime()
    if state == "absent":
        pytest.skip(f"LumiKey fingering runtime is not installed ({detail}); run scripts/setup-fingering.sh")
    if state == "broken":
        pytest.fail(f"LumiKey fingering runtime is installed but broken: {detail}", pytrace=False)

"""Locate and bootstrap a child of the embedded Python runtime."""

import ctypes
import os
import signal
import sys
from pathlib import Path


def executable(override=None):
    home = os.environ.get("PIANO_TEACHER_PYTHON_HOME")
    return (override or os.environ.get("PIANO_PYTHON")
            or (str(Path(home) / "bin/python3") if home else sys.executable))


def environment():
    root = str(Path(__file__).resolve().parents[1])
    search_path = os.pathsep.join(dict.fromkeys((root, *filter(None, sys.path))))
    return {**os.environ, "PYTHONPATH": search_path}


def bootstrap(module):
    return (
        "import sys; sys.path[:] = [path for path in sys.path if path]; "
        f"from {module} import main; main()"
    )


def exit_on_parent_death(parent):
    # Linux PR_SET_PDEATHSIG, followed by a check for death before registration.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
        raise SystemExit("Python worker parent is unavailable")

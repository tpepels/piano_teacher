"""Per-case stage state and exact-evidence result receipts."""
import hashlib
import json
import os
from pathlib import Path
import time

from . import capture_store
from .capture_store import atomic_json


def ignore_stage(stage: str) -> None:
    """Public standalone execution has no worker checkpoint to update."""


class StageRecorder:
    """A worker creates one recorder for each case, never shared process state."""

    def __init__(self, directory: Path, *, key, run_id, worker_identity):
        self.path = directory / 'case-state.json'
        self._record = dict(key=key, run_id=run_id, pid=os.getpid(), stage='starting',
                            worker_identity=worker_identity, started_at=time.time(),
                            started_monotonic=time.monotonic())

    def __call__(self, stage: str) -> None:
        self._record.update(stage=stage, updated_at=time.time())
        atomic_json(self.path, self._record)


def record_case(directory: Path, *, key, row: dict) -> None:
    witnesses = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                 for name in ('audit.json', 'fixture.json', 'score.musicxml', 'capture-manifest.json')
                 if (directory / name).is_file()}
    atomic_json(directory / 'case-result.json', dict(key=key, **row, witnesses=witnesses))


def resumable_case(directory: Path, *, key, godot_version, dependency_hash=None):
    try:
        capture_store.recover_capture_publish(directory)
        record = json.loads((directory / 'case-result.json').read_text())
        if record.get('key') != key or record.get('state') != 'completed':
            return None
        witnesses = record.get('witnesses', {})
        required = {'audit.json', 'fixture.json', 'score.musicxml', 'capture-manifest.json'}
        if set(witnesses) != required:
            return None
        for name, digest in witnesses.items():
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
                return None
        dependency_hash = dependency_hash or capture_store.capture_dependency_hash
        capture_store.validate_capture_manifest(directory, dependency_hash=dependency_hash(),
                                                 godot_version=godot_version)
        if not isinstance(record.get('result', {}).get('errors'), list):
            return None
        return dict(record, resumed=True)
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        return None

"""Isolated adapter for the published Lumikey ONNX piano models."""
from __future__ import annotations
from contextlib import suppress
import json
import os
import signal
import subprocess
from tempfile import TemporaryFile
from time import monotonic
from ..music import Piece, source_note_id
from .. import python_worker
from .model_assets import MODEL_HASHES, ONNX_RUNTIME_VERSION
from .types import Prediction

_WORKER_BOOTSTRAP = python_worker.bootstrap("piano_teacher.fingering.worker")


class LumikeyProvider:
    def __init__(self, *, executable: str | None = None, timeout: float = 300, checkpoint=None):
        self.executable = python_worker.executable(
            executable or os.environ.get("PIANO_FINGERING_PYTHON"))
        self.timeout = timeout
        self._checkpoint = checkpoint

    def _infer(self, notes):
        command = [self.executable, "-S", "-c", _WORKER_BOOTSTRAP, str(os.getpid())]
        deadline = monotonic() + self.timeout
        # A regular file survives communicate() retries, including partial
        # stdin handling on CPython 3.12. Encode in small pieces so the
        # embedded interpreter can service MIDI and clock threads meanwhile.
        with TemporaryFile(mode="w+", encoding="utf-8") as source:
            source.write('{"notes":[')
            for offset in range(0, len(notes), 128):
                self._check_running(deadline, command)
                if offset:
                    source.write(",")
                try:
                    batch = json.dumps(notes[offset:offset + 128], allow_nan=False)
                except ValueError as exc:
                    raise RuntimeError(f"Invalid local fingering request: {exc}") from exc
                source.write(batch[1:-1])
            source.write("]}")
            source.seek(0)
            self._check_running(deadline, command)
            with subprocess.Popen(
                command, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace", start_new_session=True,
                env={**python_worker.environment(), "OMP_NUM_THREADS": "1",
                     "OPENBLAS_NUM_THREADS": "1"},
            ) as process:
                try:
                    while True:
                        remaining = self._check_running(deadline, command)
                        try:
                            output, error = process.communicate(timeout=min(remaining, .05))
                        except subprocess.TimeoutExpired:
                            continue
                        self._check_running(deadline, command)
                        return process.returncode, output, error
                finally:
                    if process.returncode is None:
                        with suppress(ProcessLookupError):
                            os.killpg(process.pid, signal.SIGKILL)

    def _check_running(self, deadline, command):
        if self._checkpoint is not None:
            self._checkpoint()
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, self.timeout)
        return remaining

    @property
    def identity(self) -> dict:
        return {'name': 'lumikey', 'version': '0.3.0', 'model_version': MODEL_HASHES,
                'runtime': f'onnxruntime@{ONNX_RUNTIME_VERSION}/cpu', 'adapter_version': 6}

    def predict(self, piece: Piece, fixed: dict[str, int]) -> dict[str, Prediction]:
        notes, unknown = [], {}
        for index, n in enumerate(piece.notes):
            sid = source_note_id(n, index)
            if not 21 <= n.pitch <= 108:
                unknown[sid] = Prediction(fixed.get(sid), 'Outside pretrained piano range A0–C8')
                continue
            note = {'source_id': sid, 'note': n.pitch, 'left': n.hand == 'left',
                    'time': n.start*60000/piece.bpm,
                    'duration': (n.end-n.start)*60000/piece.bpm, 'velocity': n.velocity}
            if sid in fixed:
                note['finger'] = fixed[sid]
            notes.append(note)
        if not notes:
            return unknown
        try:
            status, output, error = self._infer(notes)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f'Local Python fingering worker unavailable: {exc}') from exc
        if status:
            error = error.strip()[-2000:]
            raise RuntimeError(f'Local fingering inference failed (exit {status}): {error}')
        try:
            entries = json.loads(output)['assignments']
            result = {entry['source_id']: Prediction(entry['finger'], entry.get('reason', '')) for entry in entries}
            if set(result) != {n['source_id'] for n in notes} or len(result) != len(notes):
                raise ValueError('Model result identity mismatch')
            for sid, prediction in result.items():
                finger = prediction.finger
                if finger is not None and (type(finger) is not int or not 1 <= finger <= 5):
                    raise ValueError('Invalid predicted finger')
                if sid in fixed and finger != fixed[sid]:
                    raise ValueError('Provider changed a fixed finger')
            return {**result, **unknown}
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f'Invalid local fingering response: {exc}') from exc

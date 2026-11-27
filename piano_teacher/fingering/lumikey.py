"""Isolated adapter for the real published Lumikey JavaScript/ONNX provider."""
from __future__ import annotations
from contextlib import suppress
import json
import os
from pathlib import Path
import signal
import subprocess
from time import monotonic
from ..music import Piece, source_note_id
from .types import Prediction

RUNTIME = Path(__file__).with_name('lumikey_runtime')
MODEL_HASHES = {
    'left': '246f2fed013c27ca8c32ce9d070002afcc49da4f1dfb0c43e09a4a3f9f2fb86e',
    'right': 'f931288302b87f5eec1c8af29a570ee0213a272a13eeb590991a285e1f1b67eb',
}


class LumikeyProvider:
    def __init__(self, *, node: str | None = None, timeout: float = 300, checkpoint=None):
        self.node = node or os.environ.get('PIANO_FINGERING_NODE', 'node')
        self.timeout = timeout
        self._checkpoint = checkpoint

    def _infer(self, notes):
        command = [self.node, str(RUNTIME/'bridge.cjs')]
        payload = json.dumps({'notes': notes})
        if self._checkpoint is not None:
            self._checkpoint()
        deadline = monotonic() + self.timeout
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, start_new_session=True,
                env={**os.environ, 'OMP_NUM_THREADS': '1'}) as process:
            try:
                while (remaining := deadline - monotonic()) > 0:
                    if self._checkpoint is not None:
                        self._checkpoint()
                    try:
                        output, error = process.communicate(payload, timeout=min(remaining, .05))
                        return process.returncode, output, error
                    except subprocess.TimeoutExpired:
                        # communicate retains its input and output buffers between attempts.
                        payload = None
                raise subprocess.TimeoutExpired(command, self.timeout)
            finally:
                if process.returncode is None:
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)

    @property
    def identity(self) -> dict:
        return {'name': 'lumikey', 'version': '0.3.0', 'model_version': MODEL_HASHES,
                'runtime': 'onnxruntime-node@1.30.0/cpu', 'adapter_version': 5}

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
            raise RuntimeError(f'Local fingering runtime unavailable: {exc}. Run scripts/setup-fingering.sh') from exc
        if status:
            error = error.strip()[-2000:]
            raise RuntimeError(f'Local fingering inference failed: {error}. Run scripts/setup-fingering.sh')
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

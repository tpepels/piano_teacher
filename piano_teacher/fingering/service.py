"""Whole-piece inference, durable user constraints and atomic reusable plans."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from threading import RLock

from ..music import Piece, source_note_id
from .types import FingerAssignment, FingeringPlan, FingeringProvider, Prediction


def _digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _read(path: Path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError, UnicodeError):
        return None


def _write(path: Path, value: dict) -> None:
    descriptor, temp = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, sort_keys=True, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class FingeringService:
    def __init__(self, directory: Path, *, provider: FingeringProvider | None = None):
        if provider is None:
            from .lumikey import LumikeyProvider
            provider = LumikeyProvider()
        self.provider = provider
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    @contextmanager
    def _locked(self, fingerprint: str):
        directory = self.directory / _digest(fingerprint)
        directory.mkdir(parents=True, exist_ok=True)
        with self._lock, (directory/'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield directory
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @staticmethod
    def _sources(piece):
        sources = {source_note_id(n, i): n for i, n in enumerate(piece.notes)}
        if len(sources) != len(piece.notes):
            raise ValueError('Original piece contains duplicate source note identities')
        if piece.bpm <= 0 or any(n.hand not in ('left', 'right') or n.end <= n.start for n in piece.notes):
            raise ValueError('Invalid source timing or hand for fingering')
        return sources

    def prepare(self, piece: Piece, fingerprint: str) -> FingeringPlan:
        with self._locked(fingerprint) as directory:
            return self._prepare(piece, fingerprint, directory)

    def correct(self, piece: Piece, fingerprint: str, source_id: str, finger: int | None) -> FingeringPlan:
        if finger is not None and (type(finger) is not int or not 1 <= finger <= 5):
            raise ValueError('Finger must be an integer from 1 to 5, or null to remove a correction')
        if source_id not in self._sources(piece):
            raise ValueError('Unknown original source note')
        with self._locked(fingerprint) as directory:
            overrides = self._overrides(directory)
            if finger is None:
                overrides.pop(source_id, None)
            else:
                overrides[source_id] = finger
            _write(directory/'overrides.json', overrides)
            return self._prepare(piece, fingerprint, directory)

    @staticmethod
    def _overrides(directory):
        value = _read(directory/'overrides.json')
        if value is None:
            if (directory/'overrides.json').exists():
                # User edits must never silently disappear on corruption.
                raise ValueError('Fingering corrections file is damaged; preserve and repair overrides.json')
            return {}
        if not isinstance(value, dict) or any(not isinstance(k, str) or type(v) is not int or not 1 <= v <= 5
                                              for k, v in value.items()):
            raise ValueError('Invalid saved fingering corrections')
        return value

    def _prepare(self, piece, fingerprint, directory):
        sources = self._sources(piece)
        overrides = {sid: finger for sid, finger in self._overrides(directory).items() if sid in sources}
        # Fingers written in an imported MusicXML score are kept as authored;
        # the learner's corrections still win, the model fills the rest.
        authored = {sid: finger for sid, finger in getattr(piece, 'authored_fingerings', ())
                    if sid in sources}
        authored_text = {sid: (str(finger),) for sid, finger in authored.items()}
        fixed = {**authored, **overrides}
        config = {'input_digest': _digest({'bpm': piece.bpm,
                    'notes': [asdict(n) for n in piece.notes], 'authored': authored_text}),
                  'manual': overrides, 'scope': 'complete-original-piece', 'schema': 1}
        provider = self.provider.identity
        cache = directory / f'plan-{_digest([provider,config])}.json'
        stored = _read(cache)
        if stored is not None:
            try:
                plan = FingeringPlan.from_dict(stored)
                if (plan.source_fingerprint == fingerprint and plan.provider == provider
                    and plan.config == config and set(plan.assignments) == set(sources)
                    and all(plan.assignments[sid].hand == n.hand
                        and plan.assignments[sid].manual == overrides.get(sid)
                        and plan.assignments[sid].authored == authored.get(sid)
                        and plan.assignments[sid].authored_text == authored_text.get(sid,())
                        and plan.assignments[sid].origin == ('manual' if sid in overrides else 'authored' if sid in authored_text else 'automatic')
                        and (sid not in fixed or plan.assignments[sid].finger == fixed[sid])
                        for sid,n in sources.items())):
                    return plan
            except (TypeError, KeyError, ValueError):
                pass  # Derived plan is disposable; durable overrides are separate.
        error = ''
        try:
            predictions = self.provider.predict(piece, fixed)
            if set(predictions) != set(sources):
                raise RuntimeError('Fingering provider omitted original source identities')
            for sid, p in predictions.items():
                if p.finger is not None and (type(p.finger) is not int or not 1 <= p.finger <= 5):
                    raise RuntimeError('Fingering provider returned an invalid finger')
                if sid in fixed and p.finger != fixed[sid]:
                    raise RuntimeError('Fingering provider changed a fixed assignment')
        except RuntimeError as exc:
            error = str(exc)
            predictions = {sid: Prediction(fixed.get(sid), error) for sid in sources}
        assignments = {}
        for sid, n in sources.items():
            p = predictions[sid]
            finger, reason = p.finger, p.reason
            assignments[sid] = FingerAssignment(sid, finger, n.hand,
                'manual' if sid in overrides else 'authored' if sid in authored_text else 'automatic',
                authored.get(sid), overrides.get(sid), authored_text.get(sid, ()), reason)
        status = 'unavailable' if error else 'partial' if any(a.finger is None or a.reason for a in assignments.values()) else 'ready'
        plan = FingeringPlan(fingerprint, provider, config, assignments, status, error)
        if not error:
            _write(cache, plan.to_dict())
        return plan

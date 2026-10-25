"""Whole-piece inference, durable user constraints and atomic reusable plans."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from fractions import Fraction
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from xml.etree import ElementTree as ET

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


def authored_fingerings(piece: Piece) -> dict[str, tuple[str, ...]]:
    """Read original attack annotations using the importer's structural IDs.

    Retain substitutions/alternates verbatim rather than guessing which finger
    they mean. Tied continuations are not new imported attacks.
    """
    if not piece.source_musicxml:
        return {}
    root = ET.fromstring(piece.source_musicxml)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    sources = {source_note_id(n, i) for i, n in enumerate(piece.notes)}
    result = {}
    for pi, part in enumerate(root.findall('part')):
        ties = {}
        for mi, measure in enumerate(part.findall('measure')):
            for ordinal, note in enumerate(measure):
                sid = f'xml-p{pi}-m{mi}-e{ordinal}'
                if note.tag != 'note' or note.find('pitch') is None or note.find('grace') is not None:
                    continue
                pitch = note.find('pitch')
                midi = (int(Fraction(pitch.findtext('octave')))+1)*12 + {
                    'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}[pitch.findtext('step')] + int(Fraction(pitch.findtext('alter','0')))
                binding = note.findtext('staff','1'), note.findtext('voice','1'), midi
                marks = note.findall('tie') or note.findall('./notations/tied')
                roles = {mark.get('type') for mark in marks}
                attack = ties.get(binding, sid) if 'stop' in roles else sid
                if 'start' in roles:
                    ties[binding] = attack
                elif 'stop' in roles:
                    ties.pop(binding, None)
                if attack not in sources:
                    continue
                fingers = note.findall('./notations/technical/fingering')
                if fingers:
                    result[attack] = result.get(attack, ()) + tuple(('' if f.text is None else f.text.strip())
                        + (' [substitution]' if f.get('substitution') == 'yes' else '')
                        + (' [alternate]' if f.get('alternate') == 'yes' else '') for f in fingers)
    return result


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
        authored_text = authored_fingerings(piece)
        authored = {}
        for sid, raw in authored_text.items():
            simple = {text for text in raw if text in ('1','2','3','4','5')}
            if len(simple) == 1:
                authored[sid] = int(next(iter(simple)))
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
            if sid in authored_text and sid not in fixed:
                finger, reason = None, 'Authored fingering has no single primary finger; choose an explicit correction'
            elif sid in authored and any(text not in ('1','2','3','4','5') for text in authored_text[sid]):
                reason = reason or 'Additional authored fingering annotations retained; only the primary attack finger is displayed'
            assignments[sid] = FingerAssignment(sid, finger, n.hand,
                'manual' if sid in overrides else 'authored' if sid in authored_text else 'automatic',
                authored.get(sid), overrides.get(sid), authored_text.get(sid, ()), reason)
        status = 'unavailable' if error else 'partial' if any(a.finger is None or a.reason for a in assignments.values()) else 'ready'
        plan = FingeringPlan(fingerprint, provider, config, assignments, status, error)
        if not error:
            _write(cache, plan.to_dict())
        return plan

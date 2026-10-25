"""Provider-neutral original-piece fingering contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from ..music import Piece


@dataclass(frozen=True)
class Prediction:
    finger: int | None
    reason: str = ''


class FingeringProvider(Protocol):
    @property
    def identity(self) -> dict: ...

    def predict(self, piece: Piece, fixed: dict[str, int]) -> dict[str, Prediction]: ...


@dataclass(frozen=True)
class FingerAssignment:
    source_id: str
    finger: int | None
    hand: str
    origin: str = 'automatic'
    authored: int | None = None
    manual: int | None = None
    authored_text: tuple[str, ...] = ()
    reason: str = ''


@dataclass(frozen=True)
class FingeringPlan:
    source_fingerprint: str
    provider: dict
    config: dict
    assignments: dict[str, FingerAssignment]
    status: str = 'ready'
    error: str = ''
    schema: int = 1

    def summary(self) -> dict:
        known = sum(a.finger is not None for a in self.assignments.values())
        return {'status': self.status, 'provider': self.provider,
                'source_fingerprint': self.source_fingerprint,
                'assigned': known, 'unknown': len(self.assignments)-known,
                'manual': sum(a.manual is not None for a in self.assignments.values()),
                'review': sum(a.finger is not None and bool(a.reason) for a in self.assignments.values()),
                'issues': list(dict.fromkeys(a.reason for a in self.assignments.values() if a.reason))[:8],
                'error': self.error}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> FingeringPlan:
        if not isinstance(value, dict) or value.get('schema') != 1:
            raise ValueError('Unsupported fingering plan version')
        if (not isinstance(value.get('assignments'), dict)
                or not isinstance(value.get('provider'), dict)
                or not isinstance(value.get('config'), dict)
                or not isinstance(value.get('source_fingerprint'), str)
                or value.get('status') not in ('ready','partial')
                or not isinstance(value.get('error'), str)):
            raise ValueError('Malformed derived fingering plan')
        assignments = {}
        for key, raw in value['assignments'].items():
            if (not isinstance(raw, dict) or not isinstance(raw.get('authored_text',[]), (list,tuple))
                    or any(not isinstance(t,str) for t in raw.get('authored_text',[]))):
                raise ValueError('Malformed derived fingering assignment')
            a = FingerAssignment(**{**raw, 'authored_text': tuple(raw.get('authored_text', ()))})
            if (key != a.source_id or a.hand not in ('left', 'right')
                    or a.origin not in ('manual','authored','automatic')
                    or not isinstance(a.reason,str) or a.finger is None and not a.reason):
                raise ValueError('Invalid fingering identity')
            for finger in (a.finger, a.authored, a.manual):
                if finger is not None and (type(finger) is not int or not 1 <= finger <= 5):
                    raise ValueError('Invalid stored finger')
            assignments[key] = a
        return cls(**{**value, 'assignments': assignments})

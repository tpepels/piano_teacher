"""Typed immutable inputs to the single serialized desktop practice session.

These are source/take/physical actions, not a second musical clock,
background event bus or persisted event stream. Every accepted mutation
still executes through PracticeSession.apply under the session RLock.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class TimedStartRequested:
    arguments: dict


@dataclass(frozen=True, slots=True)
class UserCommand:
    action: str
    parameters: dict


@dataclass(frozen=True, slots=True)
class ClockAdvanced:
    """One native worker clock tick."""


@dataclass(frozen=True, slots=True)
class MidiShortcut:
    """Accepted keyboard-control gesture, not a grading event."""
    effect: object


@dataclass(frozen=True, slots=True)
class PhysicalMidi:
    message: object
    received_at: float | None = None
    corrected_at: float | None = None
    deferred: bool = False



@dataclass(frozen=True, slots=True)
class PresentationRequired:
    """Desktop requests physical admission before any timed grading."""


@dataclass(frozen=True, slots=True)
class PlaybackReserved:
    receipt: dict


@dataclass(frozen=True, slots=True)
class PlaybackPresented:
    receipt: dict


@dataclass(frozen=True, slots=True)
class PlaybackWithdrawn:
    receipt: dict


@dataclass(frozen=True, slots=True)
class PlaybackFailed:
    failure: dict


@dataclass(frozen=True, slots=True)
class SourceCommitted:
    prepared: object
    warmup: bool
    opened_identifier: str | None = None


@dataclass(frozen=True, slots=True)
class SettingsChanged:
    changes: dict


@dataclass(frozen=True, slots=True)
class DeviceSelected:
    name: str


@dataclass(frozen=True, slots=True)
class PreloadReady:
    stage_key: str
    revision: int


@dataclass(frozen=True, slots=True)
class PreloadFailed:
    fingerprint: str
    step_number: int
    revision: int
    error: str


@dataclass(frozen=True, slots=True)
class CalibrationRequested:
    action: str


@dataclass(frozen=True, slots=True)
class HardwareRequested:
    action: str


@dataclass(frozen=True, slots=True)
class HistoryExported:
    path: str
    include_detail: bool


@dataclass(frozen=True, slots=True)
class PieceHistoryDeleted:
    fingerprint: str
    confirm: bool


@dataclass(frozen=True, slots=True)
class LearnerHistoryDeleted:
    confirm: bool


@dataclass(frozen=True, slots=True)
class SessionClosed:
    """Close ledger/device after the final active-take interruption."""


PracticeEvent = (TimedStartRequested | UserCommand | ClockAdvanced |
                 PhysicalMidi | MidiShortcut |
                 PresentationRequired | PlaybackReserved | PlaybackPresented |
                 PlaybackWithdrawn | PlaybackFailed | SourceCommitted |
                 SettingsChanged | DeviceSelected | PreloadReady | PreloadFailed |
                 SessionClosed | CalibrationRequested | HardwareRequested |
                 HistoryExported | PieceHistoryDeleted | LearnerHistoryDeleted)



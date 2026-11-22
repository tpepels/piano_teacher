"""Frozen event envelopes for the one serialized desktop practice session.

Payload dictionaries, MIDI messages and prepared-source objects are not
deep-frozen: they are consumed immediately while holding the application
lock, with source/revision/receipt identity validated by the domain.
No separate timer, event bus or persisted event log is introduced.
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
class ImmediateTransition:
    """Session-owned follow-up to a transition committed in this worker tick."""


@dataclass(frozen=True, slots=True)
class MidiShortcut:
    """Accepted keyboard-control gesture, not a grading event."""
    effect: object


@dataclass(frozen=True, slots=True)
class MidiArrival:
    """Committed device/source/take epoch sampled at physical callback."""
    device: str
    fingerprint: str
    revision: int
    stage_key: str
    hand: str
    transport_id: int
    cancellation_generation: int
    automatic: bool


@dataclass(frozen=True, slots=True)
class PhysicalMidi:
    message: object
    received_at: float | None = None
    corrected_at: float | None = None
    deferred: bool = False
    arrival: MidiArrival | None = None



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
class FingeringCorrectionCommitted:
    corrected: object


@dataclass(frozen=True, slots=True)
class SettingsChanged:
    changes: dict


@dataclass(frozen=True, slots=True)
class MidiPortsRequested:
    """Probe MIDI ports and reconcile a disconnected/preferred device."""


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
                 FingeringCorrectionCommitted | SettingsChanged |
                 MidiPortsRequested | DeviceSelected |
                 PreloadReady | PreloadFailed |
                 SessionClosed | CalibrationRequested | HardwareRequested |
                 HistoryExported | PieceHistoryDeleted | LearnerHistoryDeleted)



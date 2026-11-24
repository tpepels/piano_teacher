"""Frozen musical source and transport observation for playback admission."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from ..music import Phrase
from .playback_transitions import CountInPlan

@dataclass(frozen=True, slots=True)
class PlaybackSourceFacts:
    fingerprint: str
    stage_key: str
    revision: int
    hand: str
    bpm: float
    end_beat: float
    count_in_bar_beats: float
    count_in_meter: tuple[int, int]
    tempo_segments: tuple[tuple[float,float,float],...]

@dataclass(frozen=True, slots=True)
class PlaybackRuntimeFacts:
    source: PlaybackSourceFacts | None
    now: float
    mode: str
    running: bool
    paused: bool
    run_at: float
    paused_at: float
    play_from_beat: float
    resume_grading_after: float
    pause_context: str | None
    pending_result: bool
    transport_id: int


@dataclass(frozen=True, slots=True)
class TimedTakeSource:
    phrase: Phrase
    boundaries: tuple[float, ...]
    time_signatures: tuple
    bpm: float
    visual_gap_beats: float


@dataclass(frozen=True, slots=True)
class TimedStartRequest:
    mode: str
    position: float
    automatic: bool
    connected: bool
    loop_continuation: bool = False
    scheduled_deadline: float | None = None
    presentation_lead_seconds: float = 0.0
    count_in_plan: CountInPlan | None = None


@dataclass(frozen=True, slots=True)
class StartedTake:
    scope: str
    from_beat: float
    end_beat: float
    next_boundary_beat: float
    run_at: float
    next_action: str


@dataclass(frozen=True, slots=True)
class PreparationRequest:
    source_model: dict
    target: float
    now: float
    from_visual: float
    reverse_seconds: float
    bpm: float
    horizon_beats: float
    reading_lead_included: bool = False
    announce: bool = True
    short_deadline: float | None = None


@dataclass(frozen=True, slots=True)
class ListenActivation:
    requested_count_in: float | None = None
    from_beat: float = 0.0


@dataclass(frozen=True, slots=True)
class ResumeRequest:
    learning: bool
    bpm: float | None
    full_count_in_beats: float
    midi_connected: bool
    reading_lead_seconds: float = 0.0
    scheduled_deadline: float | None = None


@dataclass(frozen=True, slots=True)
class ResumedTimeline:
    now: float
    learning: bool
    previous_origin: float
    shift_run_at: bool


@dataclass(frozen=True, slots=True)
class ResumeCompletion:
    feedback: str | None
    deferred_score_revision: int | None


@dataclass(frozen=True, slots=True)
class FullPassageFacts:
    pending: Any
    stage_key: str
    bpm: float
    target_bpm: float
    assessed_bpm: float | None
    duration: float
    now: float
    source_model: dict


@dataclass(frozen=True, slots=True)
class PassageCompletion:
    advance_feedback: bool = False
    force_early: bool = False
    update_clock: bool = False
    next_action: str | None = None


@dataclass(frozen=True, slots=True)
class PassageRuntimeFacts:
    automatic: bool
    run_at: float
    from_beat: float


@dataclass(frozen=True, slots=True)
class PassageFinishPlan:
    action: str  # "stop" | "ready" | "announce"
    deadline: float | None = None
    next_action: str | None = None


@dataclass(frozen=True, slots=True)
class ScheduledContinuation:
    from_beat: float


@dataclass(frozen=True, slots=True)
class AppliedContinuation:
    start: ScheduledContinuation | None = None
    feedback: str | None = None


@dataclass(frozen=True, slots=True)
class PreloadedFeedbackSource:
    duration_beats: float
    bpm: float
    tempo: Any


@dataclass(frozen=True, slots=True)
class PlaybackAuthorization:
    action: str
    deadline: float
    transition: Any = None

    def validate_selected(self, selected, intent) -> None:
        expected = self.transition.exposure
        if (selected != expected or selected.stage_key != intent.stage_key
                or selected.hand != intent.hand
                or abs(selected.from_beat-intent.from_beat) > 1e-7):
            raise ValueError("Selected playback transition changed before admission")

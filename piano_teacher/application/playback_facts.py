"""Frozen musical source and transport observation for playback admission."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from ..music import Phrase
from .playback_transitions import CountInPlan
from .musical_scheduler import RestMeasurement

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
    preview_only: bool
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
class HeadlessStartTiming:
    deadline: float | None
    lead_seconds: float


@dataclass(frozen=True, slots=True)
class ListenActivation:
    started: bool = False
    requested_count_in: float | None = None
    from_beat: float = 0.0


@dataclass(frozen=True, slots=True)
class ResumeRequest:
    learning: bool
    bpm: float | None
    full_count_in_beats: float
    midi_connected: bool
    reading_lead_seconds: float = 0.0
    reuse_pending_score: bool = False
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
    total_beats: float
    duration: float
    now: float
    visual_from: float
    feedback_seconds: float
    source_model: dict
    presentation_bpm: float
    horizon_beats: float
    warmup: bool
    presentation_required: bool
    short_rest_enabled: bool
    retry_rest: RestMeasurement | None
    repeat_rest: RestMeasurement | None
    assets_ready: bool
    exact_repeats: bool = False


@dataclass(frozen=True, slots=True)
class PassageCompletion:
    advance_feedback: bool = False
    force_early: bool = False
    update_clock: bool = False
    next_action: str | None = None


@dataclass(frozen=True, slots=True)
class PassageRuntimeFacts:
    automatic: bool
    retry_previous_pass: bool
    run_at: float
    from_beat: float
    gap_beats: float


@dataclass(frozen=True, slots=True)
class PassageFinishPlan:
    preparation: PreparationRequest | None
    stop_automatic: bool
    action: str
    deadline: float | None = None
    next_action: str | None = None
    advance_early: bool = False


@dataclass(frozen=True, slots=True)
class ScheduledContinuation:
    from_beat: float
    deadline: float


@dataclass(frozen=True, slots=True)
class AppliedContinuation:
    start: ScheduledContinuation | None = None
    feedback: str | None = None


@dataclass(frozen=True, slots=True)
class RestResumeFacts:
    now: float
    reading_lead_seconds: float
    running: bool
    mode: str
    bpm: float | None
    presentation_bpm: float
    horizon_beats: float
    physical_rest_enabled: bool
    rest: RestMeasurement | None
    reuse: bool


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

    def validate_installed(self, selected, intent) -> None:
        expected = self.transition.exposure
        if (selected != expected or selected.stage_key != intent.stage_key
                or selected.hand != intent.hand
                or abs(selected.from_beat-intent.from_beat) > 1e-7):
            raise ValueError("Selected playback transition changed before admission")

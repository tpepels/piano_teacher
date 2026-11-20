"""Frozen musical source and transport observation for playback admission."""
from __future__ import annotations
from dataclasses import dataclass

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

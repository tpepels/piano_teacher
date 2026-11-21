"""Single state projection owner for future score and guided Free targets.

The practice engine captures immutable source and transport facts under its
lock. Publishing a snapshot may not start playback, change teaching progress
or invent a second graphical deadline. This service owns the persistent
guided display epoch. Headless fixture projection has a separate adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from .musical_scheduler import SCHEDULER


@dataclass(frozen=True, slots=True)
class ScoreProjectionFacts:
    fingerprint: str
    stage_key: str
    revision: int
    transport_id: int
    mode: str
    running: bool
    paused: bool
    awaiting_score: bool
    bpm: float
    presentation_bpm: float
    run_at: float
    play_from_beat: float
    announced: tuple | None
    announced_deadline: float | None
    announcement_serial: int
    scheduled_start: tuple | None
    timeline: dict
    next_count_in_beats: float
    next_count_in_meter: tuple[int, int]
    continuous_horizon_beats: float
    duration_beats: float
    has_source: bool


class ScoreStatePublisher:
    """One snapshot presentation policy; never authorizes a take."""

    def __init__(self):
        self.guided_deadline: float | None = None
        self.guided_source: tuple[str, str, int, int] | None = None

    def reset_guided(self) -> None:
        self.guided_deadline = None
        self.guided_source = None

    def prepare_guided(self, state: dict, facts: ScoreProjectionFacts,
                       *, now: float) -> None:
        # The guided plan's deadline belongs to one precise authenticated
        # musical source. A new window can enter Free without going through
        # a mode change, so an old (possibly expired) deadline cannot be
        # reused solely because a prior plan was already calculated.
        source = (facts.fingerprint, facts.stage_key,
                  facts.revision, facts.transport_id)
        if source != self.guided_source:
            self.guided_source = source
            self.guided_deadline = None
        if (not facts.has_source or facts.mode != "learn" or facts.paused
                or facts.awaiting_score or state.get("phase") not in
                    ("guided_wait", "introducing", "disconnected")):
            return
        if state.get("phase") != "guided_wait" or self.guided_deadline is None:
            self.guided_deadline = SCHEDULER.guided(
                now=now, previous_deadline=self.guided_deadline,
                duration_beats=max(.25,facts.duration_beats),
                count_in_beats=facts.next_count_in_beats,
                horizon_beats=facts.continuous_horizon_beats,bpm=facts.bpm)

    def _guided_plan(self, state: dict, facts: ScoreProjectionFacts) -> dict | None:
        if (not facts.has_source or facts.mode != "learn" or facts.paused
                or facts.awaiting_score or self.guided_deadline is None
                or self.guided_source != (
                    facts.fingerprint, facts.stage_key,
                    facts.revision, facts.transport_id)
                or state.get("phase") not in
                    ("guided_wait", "introducing", "disconnected")):
            return None
        key = (f"guided:{facts.fingerprint}:{facts.stage_key}:"
               f"{facts.revision}:{facts.transport_id}:"
               f"{self.guided_deadline:.6f}")
        return {
            "segment_id":key,"plan_id":key,"source_from_beat":0.0,
            "deadline_at_ms":self.guided_deadline*1000.0,
            "transport_id":facts.transport_id,
            "count_in_beats":facts.next_count_in_beats,
            "count_in_meter":list(facts.next_count_in_meter),
            "bpm":facts.bpm}

    def publish(self, state: dict, facts: ScoreProjectionFacts) -> dict | None:
        """Project authorized desktop score facts. Never construct a headless plan."""
        guided = self._guided_plan(state, facts)
        if not facts.timeline:
            return guided
        # All desktop take intents and receipts originate in PlaybackCoordinator.
        state["playback_intent"] = facts.timeline["intent"]
        state["playback_timeline"] = facts.timeline["current"]
        if (facts.timeline["intent"] is not None
                and not facts.running and not facts.paused):
            # A successor can be physically prepared while an older take
            # continues playing or is paused. "admitting" describes
            # an idle transport waiting for its first authorized source;
            # it must never overwrite the active take's actual phase.
            state["phase"] = "admitting"
        elif (facts.timeline["current"].get("state") == "failed"
              and not facts.running):
            # Project the transaction owner's terminal error in the same
            # read model used by the practice screen. This makes Retry
            # available again instead of indefinitely showing "admitting".
            state["feedback"] = (facts.timeline["current"].get("failure")
                                 or "The score could not be admitted")
            state["next_action"] = "Retry the passage or choose other music"
        if guided is not None:
            state["playback_timeline"]["guided"] = guided
        return guided

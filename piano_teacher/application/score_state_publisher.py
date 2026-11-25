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
    timeline: dict
    next_count_in_beats: float
    next_count_in_meter: tuple[int, int]
    duration_beats: float
    has_source: bool
    free_travel_beats: float = 0.0


class ScoreStatePublisher:
    """One snapshot presentation policy; never authorizes a take."""

    # Free's first target travels in untimed: on a slow piece it moves
    # faster than the tempo rather than taking many seconds to arrive.
    MAX_FREE_TRAVEL_SECONDS = 3.0

    def __init__(self):
        self.guided_deadline: float | None = None
        self.guided_source: tuple[str, str, int, int] | None = None
        self.guided_travel_beats = 0.0

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
            self.guided_travel_beats = max(1.0, facts.next_count_in_beats, facts.free_travel_beats)
            self.guided_deadline = SCHEDULER.guided(
                max_lead_seconds=self.MAX_FREE_TRAVEL_SECONDS,
                now=now, previous_deadline=self.guided_deadline,
                duration_beats=max(.25,facts.duration_beats),
                # At least one bar, and long enough for the target to come
                # in from off-screen: the staff must hold where it is drawn.
                count_in_beats=max(facts.next_count_in_beats,facts.free_travel_beats),
                horizon_beats=0.0,bpm=facts.bpm)

    def guided_travel(self, source: tuple[str, str, int, int]) -> float | None:
        """Beats Free's first target travels to the playhead, for `source`."""
        return self.guided_travel_beats if source == self.guided_source else None

    def guided_open_at(self, source: tuple[str, str, int, int]) -> float | None:
        """When the published Free target reaches the playhead, for `source`."""
        return self.guided_deadline if source == self.guided_source else None

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

    @staticmethod
    def project_transport_state(state: dict, pending: dict | None,
                                timeline: dict, *, running: bool,
                                paused: bool) -> None:
        """One read-only transaction-status projection for UI and commands.

        The visible frame and a locked user gesture must see the same
        pending admission and failure, even though the control snapshot
        deliberately does not render or prepare scores.
        """
        state["playback_intent"] = pending
        state["playback_timeline"] = timeline
        if pending is not None and not running and not paused:
            # A future successor does not overwrite the current live or
            # paused take's phase until the physical presentation is bound.
            state["phase"] = "admitting"
        elif timeline.get("state") == "failed" and not running:
            state["feedback"] = (timeline.get("failure")
                                 or "The score could not be admitted")
            state["next_action"] = "Retry the passage or choose other music"

    def publish(self, state: dict, facts: ScoreProjectionFacts) -> dict | None:
        """Project authorized desktop score motion and the guided target."""
        guided = self._guided_plan(state, facts)
        # SessionReadModels already projected one canonical committed
        # transport status for both command and frame reads. This method
        # contributes only score motion and the source-bound Free target.
        # Pure projection callers can inspect motion without a full session.
        if facts.timeline and guided is not None and "playback_timeline" in state:
            state["playback_timeline"]["guided"] = guided
        return guided

"""Single state projection owner for future score and guided Free targets.

The practice engine captures immutable source and transport facts under its
lock. Publishing a snapshot may not start playback, change teaching progress
or invent a second graphical deadline. This service owns the persistent
guided display epoch and the explicit headless compatibility projection.
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

    def reset_guided(self) -> None:
        self.guided_deadline = None

    def _guided_plan(self, state: dict, facts: ScoreProjectionFacts,
                     *, now: float) -> dict | None:
        if (not facts.has_source or facts.mode != "learn" or facts.paused
                or facts.awaiting_score or
                state.get("phase") not in
                    ("guided_wait", "introducing", "disconnected")):
            return None
        duration = max(.25,facts.duration_beats)
        if (state.get("phase") != "guided_wait"
                or self.guided_deadline is None):
            self.guided_deadline = SCHEDULER.guided(
                now=now, previous_deadline=self.guided_deadline,
                duration_beats=duration,
                count_in_beats=facts.next_count_in_beats,
                horizon_beats=facts.continuous_horizon_beats,
                bpm=facts.bpm)
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

    def publish(self, state: dict, facts: ScoreProjectionFacts,
                *, now: float, measure_at) -> None:
        guided = self._guided_plan(state,facts,now=now)
        if facts.timeline:
            # Desktop: transport intent/receipts were calculated in the
            # coordinator and physically admitted by Godot. There is no
            # retrospective score_queue_next or backend stage preflight.
            state["playback_intent"] = facts.timeline["intent"]
            state["playback_timeline"] = facts.timeline["current"]
            if facts.timeline["intent"] is not None:
                state["phase"] = "admitting"
            if guided is not None:
                state["playback_timeline"]["guided"] = guided
            return
        # Headless-only adapter: source plans are observable for commands
        # and recording fixtures, never accepted as physical admission.
        floor = deadline = serial = None
        transport = facts.transport_id + 1
        rate = facts.bpm
        if (facts.mode == "practice" and not facts.paused
                and not facts.running and facts.announced is not None
                and facts.announced_deadline is not None):
            floor,deadline,rate = (float(facts.announced[0]),
                                   float(facts.announced[1])*1000.0,
                                   float(facts.announced[2]))
            serial = facts.announcement_serial
        elif (facts.mode == "practice" and facts.running
                and facts.scheduled_start is not None):
            actual_id,source_at,when,key,rev,stamp = facts.scheduled_start
            if (actual_id == facts.transport_id
                    and key == facts.stage_key and rev == facts.revision):
                floor,deadline,transport,serial = (
                    float(source_at),float(when)*1000.0,
                    facts.transport_id,stamp)
        elif (facts.mode in ("listen","perform") and facts.running
                and not facts.paused and facts.has_source):
            floor,deadline,transport = (
                facts.play_from_beat,facts.run_at*1000.0,
                facts.transport_id)
        elif guided is not None:
            floor,deadline,transport = (
                0.0,float(guided["deadline_at_ms"]),facts.transport_id)
        if (floor is None and facts.has_source and facts.running
                and not facts.paused
                and facts.mode in ("practice","perform","listen")):
            floor,deadline,transport = (
                facts.play_from_beat,facts.run_at*1000.0,
                facts.transport_id)
        if not facts.has_source or floor is None or deadline is None:
            return
        bar_beats,meter,begin_rate = measure_at(floor,rate)
        state["score_queue_next"] = {
            "plan_id":(f"{facts.fingerprint}:{facts.stage_key}:"
                f"{facts.revision}:{transport}:{floor:.6f}:"+
                (f"a{serial}" if serial is not None
                 else f"{deadline:.3f}")),
            "source_from_beat":float(floor),
            "deadline_at_ms":float(deadline),
            "transport_id":int(transport),
            "count_in_beats":SCHEDULER.count_in_beats(
                bar_beats,rate) if bar_beats > 0 and rate > 0 else 0.0,
            "bpm":float(rate),
            "start_rate_bpm":float(begin_rate),
            "count_in_meter":list(meter),
        }

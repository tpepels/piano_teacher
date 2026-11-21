"""Backend selection of one downbeat from uncommitted renderer feasibility.

Godot reports the earliest physically feasible world placement *without*
arming ink. Python chooses the one musical deadline from that lower bound,
count-in and previous take's immutable continuation. Only after this
reservation does the renderer physically commit the exact corresponding
world; playback.present validates the attested placement before the
application authorizes grading or sound.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .musical_scheduler import SCHEDULER, SNAPSHOT_LATENCY_SECONDS

MAX_EVIDENCE_AGE_MS = 1800.0
MAX_FUTURE_CLOCK_SKEW_MS = 25.0
FIXED_WORLD_ROUNDING_MS = 5.0


@dataclass(frozen=True, slots=True)
class PhysicalAdmissionEvidence:
    sampled_at_ms: float
    travel_ms: float
    world_origin: float
    queue_generation: int
    renderer_generation: int

    def physical_deadline(self, *, now_ms: float, revision: int) -> float:
        if not all(map(math.isfinite, (
                self.sampled_at_ms, self.travel_ms, self.world_origin, now_ms))):
            raise ValueError("Nonfinite physical score placement evidence")
        if self.travel_ms < 0:
            raise ValueError("Physical score travel must not be negative")
        if type(self.queue_generation) is not int or self.queue_generation < 0:
            raise ValueError("Invalid physical queue generation")
        if self.renderer_generation != revision:
            raise ValueError("Physical renderer belongs to an obsolete source revision")
        if (self.sampled_at_ms > now_ms + MAX_FUTURE_CLOCK_SKEW_MS
                or now_ms - self.sampled_at_ms > MAX_EVIDENCE_AGE_MS):
            raise ValueError("Stale or inconsistent score placement measurement")
        return self.sampled_at_ms + self.travel_ms


def choose_admission_deadline(intent, facts, evidence: PhysicalAdmissionEvidence,
                              *, reused_count_in: bool) -> float:
    """Select the earliest feasible musical deadline before physical arming.

    The physical measurement is an *earliest bound*, not a chosen timestamp.
    If music requires more lead, Python may select a later instant; Godot
    must then arm the exact corresponding world or explicitly withdraw.
    """
    if reused_count_in and not (
            intent.action == "resume" and intent.resume_remaining_beats > 0):
        raise ValueError("Only a paused count-in can reuse its spoken beats")
    physical_ms = evidence.physical_deadline(
        now_ms=facts.now * 1000.0, revision=intent.revision)
    required_beats = (
        intent.resume_remaining_beats if reused_count_in else
        0.0 if intent.fixed_deadline_ms is not None else
        intent.count_in_beats)
    earliest_ms = intent.earliest_deadline_ms
    if reused_count_in:
        earliest_ms = (intent.requested_at + SNAPSHOT_LATENCY_SECONDS
                       + SCHEDULER.beats_seconds(
                           intent.resume_remaining_beats, intent.bpm)) * 1000.0
    if intent.fixed_deadline_ms is not None:
        # An announced repeat has one immutable downbeat. Native geometry
        # may be feasible earlier; an actual printed arm is allowed only
        # at this already announced timestamp, never another bar later.
        if physical_ms > intent.fixed_deadline_ms + FIXED_WORLD_ROUNDING_MS:
            raise ValueError("Physical source cannot meet fixed repeat deadline")
        physical_ms = min(physical_ms, intent.fixed_deadline_ms)
    deadline = SCHEDULER.resolve(
        intent.action, now=facts.now, bpm=intent.bpm,
        count_in_beats=required_beats, latency=0.0,
        physical_at=physical_ms / 1000.0,
        earliest_at=earliest_ms / 1000.0).run_at * 1000.0
    if intent.fixed_deadline_ms is not None:
        if deadline > intent.fixed_deadline_ms + FIXED_WORLD_ROUNDING_MS:
            raise ValueError("Count-in cannot meet immutable repeat deadline")
        return float(intent.fixed_deadline_ms)
    return float(deadline)

"""Headless-only score queue projection for backend practice fixtures.

The desktop must authorize score intents with PlaybackCoordinator and obtain an
admission receipt from Godot. No production graphical stream consumes the queue
produced here; callers invoke this only without required presentation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable
from .musical_scheduler import SCHEDULER

if TYPE_CHECKING:
    from .score_state_publisher import ScoreProjectionFacts


def project_headless_score_queue(
        state: dict, facts: ScoreProjectionFacts, *,
        measure_at: Callable, guided: dict | None) -> None:
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

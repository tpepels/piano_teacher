"""Immutable, pure musical command plans.

The teaching policy selects a source exposure once. The transition planner
adapts that selection into an executable playback route without consulting
renderer state. An explicit CountInPlan then travels unchanged through
score admission, backend transport, voiced cues, and the learning ledger.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


MAX_COUNT_IN_PULSE_SECONDS = 1.5


@dataclass(frozen=True, slots=True)
class CountInPlan:
    bar_beats: float
    beats: float
    meter: tuple[int, int]
    bpm: float
    pulse_beats: float
    cue_beats: tuple[float, ...]

    @classmethod
    def create(cls, *, bar_beats: float, meter: tuple[int,int],
               bpm: float, beats: float) -> "CountInPlan":
        if (not all(math.isfinite(float(x))
                    for x in (bar_beats, bpm, beats))
                or bar_beats <= 0 or bpm <= 0 or beats < 0):
            raise ValueError("Invalid count-in plan")
        n, d = (int(meter[0]), int(meter[1]))
        if n <= 0 or d <= 0 or not math.isclose(
                float(bar_beats), n*4/d, rel_tol=0, abs_tol=1e-6):
            raise ValueError("Count-in must use authored meter")
        pulse = 1.5 if d == 8 and n in (6, 9, 12) else 4.0/d
        # Still exactly one authored bar, but a click slower than this is
        # not heard as a count-in: subdivide (compound pulses into thirds,
        # simple pulses into halves) while the bar divides evenly.
        while pulse*60.0/float(bpm) > MAX_COUNT_IN_PULSE_SECONDS:
            finer = pulse/3.0 if math.isclose(pulse, 1.5) else pulse/2.0
            if not math.isclose(beats/finer, round(beats/finer), abs_tol=1e-6):
                break
            pulse = finer
        count = round(beats/pulse)
        if not math.isclose(beats, count*pulse, rel_tol=0, abs_tol=1e-6):
            raise ValueError("Count-in has a partial unspoken pulse")
        cues = tuple(round(-beats+i*pulse, 8) for i in range(count))
        return cls(bar_beats=bar_beats,beats=beats,meter=(n,d),
                   bpm=bpm,pulse_beats=pulse,cue_beats=cues)

    def snapshot(self) -> dict:
        return {"bar_beats":self.bar_beats,"beats":self.beats,
                "meter":list(self.meter),"bpm":self.bpm,
                "pulse_beats":self.pulse_beats,
                "cue_beats":list(self.cue_beats)}


@dataclass(frozen=True, slots=True)
class PlaybackTransition:
    """Teaching effect selected before admission; never re-decide on commit."""
    action: str
    route: str
    preparation: str
    effect: object
    exposure: object

    @classmethod
    def from_effect(cls, effect, *, action: str,
                    source_changed: bool) -> "PlaybackTransition":
        exposure = effect.decision.next_exposure
        if exposure is None:
            raise ValueError("No selected exposure for the playback request")
        if exposure.mode == "listen":
            route = "listen"
        elif effect.state.route.mode == "learn" and exposure.mode == "practice":
            route = "prepare_practice"
        elif source_changed:
            route = "reload_score"
        elif exposure.mode == "learn":
            route = "learn"
        elif exposure.preparation == "rewind":
            route = "rewind"
        else:
            route = "start"
        # An active graphical retry always appends an immutable source
        # beyond exposed ink. Any prior physical rewind is an obsolete
        # presentation detail, not part of the teaching route.
        preparation = "future_rest" if exposure.preparation == "rewind" else exposure.preparation
        return cls(action=action,route=route,preparation=preparation,
                   effect=effect,exposure=exposure)

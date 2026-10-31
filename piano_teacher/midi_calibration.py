"""Three-round, audible/visual MIDI tap calibration on a fixed clock.

Four preview clicks precede each eight-tap round. The reported delay is
the median of three independent within-round medians. Tap-along includes
human reaction and speaker latency; it cannot isolate Bluetooth transport.
"""
from __future__ import annotations

from statistics import median


class MidiTapCalibration:
    bpm = 80
    count_in = 4
    ticks = 8
    rounds = 3
    period = 60.0 / bpm
    round_beats = count_in + ticks
    min_samples_per_round = 6
    max_round_jitter = .045  # seconds, median absolute deviation
    max_round_spread = .05
    max_credible_delay = .20

    def __init__(self) -> None:
        self.active = False
        self.start_at = 0.0
        self.samples: list[dict[int, float]] = [{} for _ in range(self.rounds)]
        self.result: dict | None = None

    def start(self, now: float) -> None:
        self.active = True
        self.start_at = now + 1.0  # let the screen present the starting count
        self.samples = [{} for _ in range(self.rounds)]
        self.result = None

    def cancel(self) -> None:
        self.active = False

    def observe(self, at: float) -> bool:
        if not self.active:
            return False
        beat = (at - self.start_at) / self.period
        index = round(beat)
        round_index, local_index = divmod(index, self.round_beats)
        if not (0 <= round_index < self.rounds
                and self.count_in <= local_index < self.round_beats):
            return False
        delay = at - (self.start_at + index * self.period)
        if abs(delay) > .30:
            return False
        slot = local_index - self.count_in
        if slot in self.samples[round_index]:
            return False
        self.samples[round_index][slot] = delay
        return True

    def _finish(self) -> None:
        self.active = False
        rounds = []
        failure = None
        for index, samples in enumerate(self.samples, start=1):
            values = list(samples.values())
            if len(values) < self.min_samples_per_round:
                failure = f"Round {index}: need at least six valid taps"
                rounds.append({"round": index, "samples": len(values),
                               "reliable": False})
                continue
            center = median(values)
            jitter = median(abs(t-center) for t in values)
            reliable = jitter <= self.max_round_jitter
            if not reliable and failure is None:
                failure = f"Round {index}: inconsistent timing; repeat calibration"
            rounds.append({"round": index, "samples": len(values),
                           "median_ms": round(center*1000),
                           "jitter_ms": round(jitter*1000),
                           "reliable": reliable})
        if failure is None:
            centers = [round_info["median_ms"] for round_info in rounds]
            result_ms = median(centers)
            if max(centers) - min(centers) > self.max_round_spread * 1000:
                failure = (f"Three rounds disagree: their medians span "
                           f"{max(centers)-min(centers)} ms (limit "
                           f"{round(self.max_round_spread*1000)} ms); "
                           f"repeat calibration")
            elif not 0 <= result_ms <= self.max_credible_delay * 1000:
                failure = "Delay estimate is outside the safe 0–200 ms range"
        self.result = {
            "rounds": rounds,
            "samples": sum(len(s) for s in self.samples),
            "reliable": failure is None,
            **({"estimate_ms": round(result_ms),
                "jitter_ms": max(r["jitter_ms"] for r in rounds)}
               if failure is None else {"error": failure}),
        }

    def snapshot(self, now: float) -> dict:
        beat = (now - self.start_at) / self.period
        total = self.rounds * self.round_beats
        if self.active and beat >= total:
            self._finish()
        active_beat = min(total-1e-8, max(0.0, beat))
        round_index = min(self.rounds-1, int(active_beat // self.round_beats))
        local_beat = active_beat - round_index * self.round_beats
        phase = ("finished" if not self.active else "ready" if beat < 0
                 else "count_in" if local_beat < self.count_in else "tap")
        return {
            "active": self.active, "bpm": self.bpm,
            "beat": beat, "round": round_index+1, "rounds": self.rounds,
            "phase": phase, "count_in": self.count_in,
            "countdown": (self.count_in - int(local_beat)
                          if phase == "count_in" else 0),
            "tap_number": (min(self.ticks, 1+int(local_beat-self.count_in))
                           if phase == "tap" else 0),
            "samples": sum(len(s) for s in self.samples),
            "round_samples": [len(s) for s in self.samples],
            "ticks": self.ticks, "round_beats": self.round_beats,
            "progress": min(1.0, max(0.0, beat/total)),
            "result": self.result,
        }

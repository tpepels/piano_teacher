"""Continuous five-round MIDI timing calibration on a shared monotonic clock.

A single four-beat count-in precedes five uninterrupted eight-tap rounds.
One anomalous tap per round and at most one unreliable round can be ignored.
The median across retained round medians provides the suggested correction.
Tap-along measures the combination of human timing and audio/input latency;
it cannot isolate Bluetooth hardware transport delay.
"""
from __future__ import annotations

from statistics import median


class MidiTapCalibration:
    bpm = 80
    count_in = 4
    ticks = 8
    rounds = 5
    period = 60.0 / bpm
    round_beats = ticks  # no repeated count-in
    total_beats = count_in + rounds * ticks
    min_samples_per_round = 6
    min_reliable_rounds = rounds - 1
    max_round_jitter = .045  # seconds, median absolute deviation
    max_round_spread = .05
    max_credible_delay = .20
    # A clear mistake is more than 40 ms or three median deviations away.
    tap_outlier_floor = .040
    round_outlier_floor_ms = 35

    def __init__(self) -> None:
        self.active = False
        self.start_at = 0.0
        self.samples: list[dict[int, float]] = [{} for _ in range(self.rounds)]
        self.result: dict | None = None

    def start(self, now: float) -> None:
        self.active = True
        self.start_at = now + 1.0  # give the display time to show preparation
        self.samples = [{} for _ in range(self.rounds)]
        self.result = None

    def cancel(self) -> None:
        self.active = False

    def observe(self, at: float) -> bool:
        if not self.active:
            return False
        beat = (at - self.start_at) / self.period
        index = round(beat)
        tap_index = index - self.count_in
        if not 0 <= tap_index < self.rounds * self.ticks:
            return False
        delay = at - (self.start_at + index * self.period)
        if abs(delay) > .30:
            return False
        round_index, slot = divmod(tap_index, self.ticks)
        if slot in self.samples[round_index]:
            return False  # duplicate note-on cannot replace the first event
        self.samples[round_index][slot] = delay
        return True

    def _finish(self) -> None:
        self.active = False
        rounds: list[dict] = []
        for number, sample_slots in enumerate(self.samples, start=1):
            values = list(sample_slots.values())
            entry: dict = {
                "round": number, "samples": len(values),
                "discarded_taps": 0, "reliable": False, "included": False,
            }
            if len(values) >= self.min_samples_per_round:
                center = median(values)
                deviation = median(abs(value - center) for value in values)
                worst = max(range(len(values)),
                            key=lambda index: abs(values[index] - center))
                # Do not trim an already undersampled round below the minimum.
                if (len(values) > self.min_samples_per_round
                        and abs(values[worst] - center) >
                        max(self.tap_outlier_floor, 3 * deviation)):
                    values.pop(worst)
                    entry["discarded_taps"] = 1
                center = median(values)
                jitter = median(abs(value - center) for value in values)
                entry.update(
                    median_ms=round(center * 1000),
                    jitter_ms=round(jitter * 1000),
                    accepted_samples=len(values),
                    reliable=jitter <= self.max_round_jitter,
                )
            rounds.append(entry)

        usable = [entry for entry in rounds if entry["reliable"]]
        failure = None
        if len(usable) < self.min_reliable_rounds:
            failure = "Need at least four consistent rounds; repeat calibration"
        else:
            centers = [entry["median_ms"] for entry in usable]
            center = median(centers)
            spread = median(abs(value - center) for value in centers)
            if len(usable) == self.rounds:
                worst = max(usable, key=lambda entry:
                            abs(entry["median_ms"] - center))
                if abs(worst["median_ms"] - center) > max(
                        self.round_outlier_floor_ms, 3 * spread):
                    usable.remove(worst)  # at most one whole-round outlier
            for entry in usable:
                entry["included"] = True
            centers = [entry["median_ms"] for entry in usable]
            if max(centers) - min(centers) > self.max_round_spread * 1000:
                failure = (f"Round estimates disagree by "
                           f"{max(centers) - min(centers)} ms; "
                           f"repeat calibration")
            else:
                estimate = round(median(centers))
                if not 0 <= estimate <= self.max_credible_delay * 1000:
                    failure = "Delay estimate is outside the safe 0–200 ms range"

        self.result = {
            "rounds": rounds,
            "samples": sum(len(sample_slots) for sample_slots in self.samples),
            "discarded_taps": sum(item["discarded_taps"] for item in rounds),
            "used_rounds": len(usable) if failure is None else 0,
            "discarded_rounds": self.rounds - len(usable) if failure is None else 0,
            "reliable": failure is None,
            **({"estimate_ms": estimate,
                "jitter_ms": max(item["jitter_ms"] for item in usable)}
               if failure is None else {"error": failure}),
        }

    def snapshot(self, now: float) -> dict:
        beat = (now - self.start_at) / self.period
        if self.active and beat >= self.total_beats:
            self._finish()
        active_beat = min(self.total_beats - 1e-8, max(0.0, beat))
        tap_beat = max(0.0, active_beat - self.count_in)
        round_index = min(self.rounds - 1, int(tap_beat // self.ticks))
        phase = ("finished" if not self.active else "ready" if beat < 0
                 else "count_in" if beat < self.count_in else "tap")
        return {
            "active": self.active, "bpm": self.bpm,
            # Same monotonic origin as the input callback, even without score.
            "start_at_ms": self.start_at * 1000.0,
            "sampled_at_ms": now * 1000.0,
            "beat": beat, "round": round_index + 1, "rounds": self.rounds,
            "phase": phase, "count_in": self.count_in,
            "countdown": (self.count_in - int(active_beat)
                          if phase == "count_in" else 0),
            "tap_number": (min(self.ticks, 1 + int(tap_beat % self.ticks))
                           if phase == "tap" else 0),
            "samples": sum(len(sample_slots) for sample_slots in self.samples),
            "round_samples": [len(sample_slots) for sample_slots in self.samples],
            "ticks": self.ticks, "round_beats": self.round_beats,
            "total_beats": self.total_beats,
            "progress": min(1.0, max(0.0, beat / self.total_beats)),
            "result": self.result,
        }

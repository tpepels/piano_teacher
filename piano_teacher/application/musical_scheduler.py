"""Single authority for musical deadlines and tempo/geometry conversions.

Engraving and queue admission supply *measurements* (rest clearance, header,
reading horizon, peer opening). They do not choose another MIDI deadline.
This pure planner combines those measurements with tempo, count-in, latency,
pause and existing reservations, publishing one absolute graded run_at.

All deadlines are monotonic seconds; all musical lengths are quarter beats.
A result includes its individual lower bounds for physical diagnostics.
The renderer may reject an infeasible plan; it cannot silently move it.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class MusicalDeadline:
    route: str
    run_at: float
    count_in_at: float
    bounds: tuple[tuple[str, float], ...]

    def __post_init__(self):
        if not math.isfinite(self.run_at) or not math.isfinite(self.count_in_at):
            raise ValueError("Invalid musical deadline")


@dataclass(frozen=True, slots=True)
class PreparationDeadline:
    reverse_at: float
    prepare_at: float
    run_at: float
    reverse_seconds: float


class MusicalScheduler:
    """All backend decisions about absolute musical time.

    The backend retains authority over score origin and grading. Godot keeps
    its 60 Hz *interpolation* and checks immutable physical ink, but all
    automatic, manual, recovery and handoff time bounds are resolved here.
    """

    @staticmethod
    def beats_seconds(beats: float, bpm: float) -> float:
        if not all(math.isfinite(x) for x in (beats, bpm)) or beats < 0 or bpm <= 0:
            raise ValueError("Invalid beat duration or BPM")
        return beats * 60.0 / bpm

    @staticmethod
    def seconds_beats(seconds: float, bpm: float) -> float:
        if not all(math.isfinite(x) for x in (seconds, bpm)) or seconds < 0 or bpm <= 0:
            raise ValueError("Invalid seconds or BPM")
        return seconds * bpm / 60.0

    @staticmethod
    def source_seconds(tempo_map, beat: float, bpm: float) -> float:
        """One source-tempo conversion, including authored slowdowns.

        `tempo_map` is the already-selected authoritative source map;
        callers must not treat its musical duration as constant nominal BPM.
        """
        if not math.isfinite(beat):
            raise ValueError("Invalid source beat")
        if tempo_map is None:
            return beat * 60.0 / bpm
        return tempo_map.seconds_at(beat)

    @classmethod
    def resolve(cls, route: str, *, now: float, bpm: float,
                count_in_beats: float = 0.0, latency: float = 0.0,
                physical_at: float | None = None,
                reserved_at: float | None = None,
                earliest_at: float | None = None) -> MusicalDeadline:
        """Take the MAX of independent constraints, never SUM their leads."""
        if not all(math.isfinite(x) for x in (now, bpm, count_in_beats, latency)) or (
                bpm <= 0 or count_in_beats < 0 or latency < 0):
            raise ValueError("Invalid musical scheduling facts")
        bounds = [("count_in", now + latency + cls.beats_seconds(count_in_beats, bpm))]
        for name, value in (("physical_clearance", physical_at),
                            ("renderer_reservation", reserved_at),
                            ("earliest_existing", earliest_at)):
            if value is not None:
                if not math.isfinite(value):
                    raise ValueError(f"Invalid {name} deadline")
                bounds.append((name, value))
        end = max(value for _, value in bounds)
        return MusicalDeadline(route,end,
            end-cls.beats_seconds(count_in_beats,bpm),tuple(bounds))

    @classmethod
    def initial(cls, *, now: float, bpm: float, count_in_beats: float,
                reserved_at: float | None = None,
                reading_lead_seconds: float = 0.0,
                continuation: bool = False) -> MusicalDeadline:
        if not math.isfinite(reading_lead_seconds) or reading_lead_seconds < 0:
            raise ValueError("Invalid reading lead")
        # A known, already-admitted continuation is immutable. Its own
        # count-in took place during the preceding rest; never add it again.
        if continuation and reserved_at is not None:
            return MusicalDeadline("announced",reserved_at,
                reserved_at-cls.beats_seconds(count_in_beats,bpm),
                (("renderer_reservation",reserved_at),))
        return cls.resolve("play" if not continuation else "continuation",
            now=now,bpm=bpm,count_in_beats=count_in_beats,
            reserved_at=reserved_at,
            earliest_at=now+reading_lead_seconds if reading_lead_seconds else None)

    @classmethod
    def repeat(cls, *, run_at: float, source_seconds: float,
               gap_beats: float, bpm: float) -> float:
        if not math.isfinite(run_at) or not math.isfinite(source_seconds) or source_seconds < 0:
            raise ValueError("Invalid source duration")
        return run_at+source_seconds+cls.beats_seconds(gap_beats,bpm)

    @classmethod
    def offscreen(cls, *, deadline: float, lead_beats: float,
                  bpm: float) -> float:
        if not math.isfinite(deadline) or not 0.0 <= lead_beats <= 64:
            raise ValueError("Invalid future notation reading lead")
        return deadline+cls.beats_seconds(lead_beats,bpm)

    @classmethod
    def missing_horizon(cls, *, deadline: float, rest_beats: float,
                        reading_horizon_beats: float, bpm: float) -> float:
        return cls.offscreen(deadline=deadline,
            lead_beats=max(0.0,reading_horizon_beats-rest_beats),bpm=bpm)

    @classmethod
    def short_rest(cls, *, now: float, source_end: float,
                   outgoing_bpm: float, incoming_bpm: float,
                   clear_beats: float, header_beats: float,
                   count_in_beats: float, latency: float,
                   tempo_epoch: float | None = None) -> MusicalDeadline:
        """Time authentic rest+header at outgoing tempo, with one rate change.

        If the outgoing BPM switches during the rest, integrate both
        constant-rate intervals exactly; the count-in uses incoming tempo.
        """
        if not all(math.isfinite(x) for x in (
                now,source_end,clear_beats,header_beats,latency)):
            raise ValueError("Invalid rest geometry")
        if clear_beats < 0 or header_beats < 0:
            raise ValueError("Negative rest/header clearance")
        span = clear_beats+header_beats
        physical = source_end+cls.beats_seconds(span,outgoing_bpm)
        if (tempo_epoch is not None and math.isfinite(tempo_epoch)
                and source_end < tempo_epoch < physical
                and abs(outgoing_bpm-incoming_bpm)>1e-9):
            passed = cls.seconds_beats(tempo_epoch-source_end,outgoing_bpm)
            physical = tempo_epoch+cls.beats_seconds(
                max(0.0,span-passed),incoming_bpm)
        return cls.resolve("short_rest",now=now,bpm=incoming_bpm,
            count_in_beats=count_in_beats,latency=latency,
            physical_at=physical)

    @classmethod
    def automatic(cls, *, announced_at: float | None, from_beat_matches: bool,
                  deadline: float, now: float, bpm: float,
                  rest_beats: float, horizon_beats: float,
                  short_rest_at: float | None) -> float:
        if announced_at is not None and from_beat_matches and (
                abs(announced_at-deadline)<=1e-9):
            return announced_at
        if short_rest_at is not None:
            return max(deadline,short_rest_at)
        if horizon_beats <= 0:
            return deadline
        return max(cls.missing_horizon(deadline=deadline,rest_beats=rest_beats,
                   reading_horizon_beats=horizon_beats,bpm=bpm),
                   cls.offscreen(deadline=now,lead_beats=horizon_beats,bpm=bpm))

    @classmethod
    def prepare(cls, *, now: float, reverse_seconds: float,
                rest_beats: float, horizon_beats: float, bpm: float,
                include_reading: bool, short_deadline: float | None = None,
                announce: bool = True) -> PreparationDeadline:
        if not math.isfinite(reverse_seconds) or reverse_seconds < 0:
            raise ValueError("Invalid rewind duration")
        reverse = max(.05,reverse_seconds)
        prepare = now+reverse
        base_end = prepare+cls.beats_seconds(rest_beats,bpm)
        if short_deadline is not None and announce:
            if not math.isfinite(short_deadline):
                raise ValueError("Invalid reserved rest deadline")
            end = short_deadline
            prepare = min(prepare,end)
            reverse = max(.05,min(reverse,prepare-now))
        elif short_deadline is not None:
            end = now
        elif include_reading or not announce:
            end = base_end
        else:
            end = base_end+cls.beats_seconds(max(0.,horizon_beats-rest_beats),bpm)
        return PreparationDeadline(now,prepare,end,reverse)

    @staticmethod
    def reserved_retry_reverse(*, lead_seconds: float, rest_seconds: float) -> float:
        if (not math.isfinite(lead_seconds) or not math.isfinite(rest_seconds)
                or lead_seconds <= 0 or rest_seconds <= 0
                or lead_seconds-rest_seconds+0.01 < 0.05):
            raise ValueError("Future retry reservation lacks space for one full rest")
        return max(.05,lead_seconds-rest_seconds)

    @classmethod
    def handoff(cls, *, now: float, previous_deadline: float,
                lead_beats: float, clear_beats: float | None,
                count_in_beats: float, bpm: float,
                rest_take_end: tuple[float,float] | None,
                latency: float) -> MusicalDeadline:
        if clear_beats is None or rest_take_end is None:
            return cls.initial(now=previous_deadline,bpm=bpm,count_in_beats=0.0,
                reserved_at=cls.offscreen(
                    deadline=max(previous_deadline,now),
                    lead_beats=lead_beats,bpm=bpm),
                continuation=True)
        source_end,outgoing_bpm = rest_take_end
        # Preserve the published physical reservation: the rest is
        # measured from its graded end, not from an arbitrary poll instant.
        remaining = max(0.,(clear_beats+lead_beats)-
                        cls.seconds_beats(max(0.,now-source_end),outgoing_bpm))
        physical = now+cls.beats_seconds(remaining,bpm)
        return cls.resolve("handoff",now=now,bpm=bpm,
            count_in_beats=count_in_beats,latency=latency,
            physical_at=physical)

    @classmethod
    def fresh_resume(cls, *, now: float, old_deadline: float,
                     reading_lead_seconds: float, horizon_beats: float,
                     bpm: float, short_rest_at: float | None,
                     reuse: bool) -> float:
        if not math.isfinite(reading_lead_seconds) or reading_lead_seconds < 0:
            raise ValueError("Invalid resumed reading lead")
        if reuse:
            return now+reading_lead_seconds
        floor = (short_rest_at if short_rest_at is not None
                 else cls.offscreen(deadline=now,lead_beats=horizon_beats,bpm=bpm))
        return max(now+reading_lead_seconds,floor)

    @staticmethod
    def shift_epoch(epoch: float, duration: float, *, active: bool) -> float:
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("Invalid pause duration")
        return epoch+duration if active else epoch

    @classmethod
    def late_ready(cls, *, now: float, outgoing_bpm: float,
                   extra_beats: float = 2.0) -> float:
        return cls.offscreen(deadline=now,lead_beats=extra_beats,bpm=outgoing_bpm)


SCHEDULER = MusicalScheduler()

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
from typing import NamedTuple
import math


# These values were previously an anonymous 3-tuple. A NamedTuple keeps the
# existing immutable public contract while giving every consumer named fields.
# A renderer can only draw this exact plan or explicitly reject it.
class PassagePlan(NamedTuple):
    from_beat: float
    run_at: float
    bpm: float


SNAPSHOT_LATENCY_SECONDS = .4
SETTLEMENT_SECONDS = .20


@dataclass(frozen=True, slots=True)
class MusicalDeadline:
    route: str
    deadline_at: float
    count_in_at: float
    bounds: tuple[tuple[str, float], ...]

    def __post_init__(self):
        if not math.isfinite(self.deadline_at) or not math.isfinite(self.count_in_at):
            raise ValueError("Invalid musical deadline")

    @property
    def run_at(self) -> float:
        return self.deadline_at


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
    def count_in_beats(bar_beats: float, bpm: float) -> float:
        # One authored preparation bar at every rate, including very slow
        # lessons. No independently capped count-in on any caller.
        if not all(math.isfinite(x) for x in (bar_beats,bpm)) or (
                bar_beats <= 0 or bpm <= 0):
            raise ValueError("Count-in requires positive meter and BPM")
        return float(bar_beats)

    @staticmethod
    def signed_beats_seconds(beats: float, bpm: float) -> float:
        """Signed score-relative beat delta (may precede the downbeat)."""
        if not all(math.isfinite(x) for x in (beats,bpm)) or bpm <= 0:
            raise ValueError("Invalid beat duration or BPM")
        return beats * 60.0 / bpm

    @classmethod
    def beats_seconds(cls, beats: float, bpm: float) -> float:
        if beats < 0:
            raise ValueError("Invalid negative beat duration")
        return cls.signed_beats_seconds(beats,bpm)

    @classmethod
    def seconds_per_beat(cls, bpm: float) -> float:
        return cls.beats_seconds(1.0,bpm)


    @staticmethod
    def seconds_beats(seconds: float, bpm: float) -> float:
        if not all(math.isfinite(x) for x in (seconds, bpm)) or bpm <= 0:
            raise ValueError("Invalid seconds or BPM")
        return seconds * bpm / 60.0


    @classmethod
    def elapsed_beats(cls, tempo_map, from_beat: float,
                      elapsed_seconds: float, bpm: float) -> float:
        if tempo_map is not None and elapsed_seconds >= 0:
            origin = cls.source_seconds(tempo_map,from_beat,bpm)
            return tempo_map.beat_at(origin+elapsed_seconds)-from_beat
        return cls.seconds_beats(elapsed_seconds,bpm)

    @staticmethod
    def tempo_epoch(*, stage: str, bpm: float, now: float,
                    prior_key: tuple | None, prior_epoch: float | None
                    ) -> tuple[tuple, float | None]:
        """The only clock epoch at which a teaching speed change occurs."""
        if not math.isfinite(now) or not math.isfinite(bpm) or bpm <= 0:
            raise ValueError("Invalid tempo transition")
        key=(stage,float(bpm))
        return (key,now) if key != prior_key else (key,prior_epoch)

    @staticmethod
    def passage(*, from_beat: float, deadline: float, bpm: float) -> PassagePlan:
        if not all(math.isfinite(x) for x in (from_beat,deadline,bpm)) or (
                from_beat < 0 or bpm <= 0):
            raise ValueError("Invalid immutable passage plan")
        return PassagePlan(float(from_beat),float(deadline),float(bpm))

    @classmethod
    def retime_passage(cls, source: PassagePlan, *, deadline: float
                       ) -> PassagePlan:
        return cls.passage(from_beat=source.from_beat,
                           deadline=deadline,bpm=source.bpm)

    @classmethod
    def shift_passage(cls, source: PassagePlan, *, seconds: float
                      ) -> PassagePlan:
        return cls.retime_passage(source,deadline=cls.shift_epoch(
            source.run_at,seconds,active=True))

    @staticmethod
    def source_seconds(tempo_map, beat: float, bpm: float) -> float:
        """One source-tempo conversion, including authored slowdowns.

        `tempo_map` is the already-selected authoritative source map;
        callers must not treat its musical duration as constant nominal BPM.
        """
        if not math.isfinite(beat):
            raise ValueError("Invalid source beat")
        if tempo_map is None:
            return MusicalScheduler.signed_beats_seconds(beat,bpm)
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

    @classmethod
    def resume_playing(cls, *, now: float, origin: float, bpm: float,
                       count_in_beats: float, reading_lead_seconds: float,
                       already_waiting: float) -> tuple[float, float]:
        """Move a paused graded take and its one count-in together.

        Only the missing reading lead is added; a lead already
        published is never charged twice. Every physical Resume
        creates a new source and full-bar preparation count-in.
        """
        total_lead = max(cls.beats_seconds(count_in_beats,bpm),
                         reading_lead_seconds)
        additional = max(0.0,total_lead-already_waiting)
        return origin+additional,now+max(total_lead,already_waiting)

    @staticmethod
    def shift_epoch(epoch: float, duration: float, *, active: bool) -> float:
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("Invalid pause duration")
        return epoch+duration if active else epoch

    @classmethod
    def guided(cls, *, now: float, previous_deadline: float | None,
               duration_beats: float, count_in_beats: float,
               horizon_beats: float, bpm: float) -> float:
        """Source-bound untimed guided repeat, using one absolute deadline."""
        lead = cls.beats_seconds(max(count_in_beats,1.0),bpm)
        distance = cls.beats_seconds(
            duration_beats+max(2.0,horizon_beats),bpm)
        if previous_deadline is None:
            return now+lead
        if now > previous_deadline+distance:
            return max(now+lead,previous_deadline+distance+lead)
        return previous_deadline


SCHEDULER = MusicalScheduler()

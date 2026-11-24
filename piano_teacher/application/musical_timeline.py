"""One declared musical timeline on the world-beat line (ROADMAP T1-T6).

A run of timed music -- count-in bars, takes and the rests between them --
is a list of contiguous segments. Each segment has a world start in beats, a
start time and its tempo spans (constant or eased, tempo_curve.py). Time and
world position are a pure function of the segments, so Python (grading) and
Godot (drawing, clicks) evaluate the same mapping; godot/musical_timeline.gd
implements the same evaluation.

Times are "musical seconds": the shared monotonic clock minus the pauses
(holds) that ended before it. A Pause freezes the world; Resume records how
long it lasted, which moves every later segment without rewriting any.

Placement is bar arithmetic: the next take starts after the last sounding
note of the previous take (ties included) rounded up to its barline, then
one count-in bar whose first half eases from the old to the new tempo. A
decision that arrives too late for that count-in adds whole rest bars.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

from .tempo_curve import TempoSpan, count_in_spans

# An appended count-in may start this much in the past (the decision is
# taken one worker tick after a take ends; Godot plays a late first click).
LATE_GRACE_SECONDS = 0.25
# A new run's count-in starts at least this long after the request, so the
# state carrying it reaches Godot before the first click.
RUN_LEAD_SECONDS = 0.35
# Past segments kept in the published snapshot (their ink is still leaving).
KEPT_PAST_SEGMENTS = 6


@dataclass(frozen=True, slots=True)
class TimelineSegment:
    kind: str                       # "count_in" | "take" | "rest"
    world_start: float              # world beats
    start_at: float                 # musical seconds
    spans: tuple[TempoSpan, ...]
    take_id: str = ""
    mode: str = ""
    source_from_beat: float = 0.0
    # A take: silence from its last sounding note to the following barline.
    rest_after_beats: float = 0.0
    meter: tuple[int, int] = (4, 4)
    # A take cut short by Resume (its remainder continues in a new take).
    cut_beats: float | None = None

    def __post_init__(self):
        if self.kind not in ("count_in", "take", "rest"):
            raise ValueError("Unknown timeline segment kind")
        if not self.spans or not all(map(math.isfinite, (
                self.world_start, self.start_at))):
            raise ValueError("Invalid timeline segment")

    @property
    def beats(self) -> float:
        total = sum(span.beats for span in self.spans)
        return total if self.cut_beats is None else min(total, self.cut_beats)

    def seconds_at(self, beats: float) -> float:
        """Seconds from the segment start until `beats` into it."""
        beats = min(self.beats, max(0.0, beats))
        elapsed = 0.0
        for span in self.spans:
            if beats <= span.beats:
                return elapsed + span.seconds_at(beats)
            elapsed += span.seconds
            beats -= span.beats
        return elapsed

    def beat_at(self, seconds: float) -> float:
        """Beats into the segment after `seconds` (clamped to it)."""
        if seconds <= 0:
            return 0.0
        passed = 0.0
        for span in self.spans:
            if seconds <= span.seconds:
                return min(self.beats, passed + span.beat_at(seconds))
            seconds -= span.seconds
            passed += span.beats
        return self.beats

    def bpm_at(self, beats: float) -> float:
        for span in self.spans:
            if beats < span.beats:
                return span.bpm_at(beats)
            beats -= span.beats
        last = self.spans[-1]
        return last.bpm_at(last.beats)

    @property
    def seconds(self) -> float:
        return self.seconds_at(self.beats)

    @property
    def end_at(self) -> float:
        return self.start_at + self.seconds

    @property
    def world_end(self) -> float:
        return self.world_start + self.beats

    @property
    def end_bpm(self) -> float:
        return self.bpm_at(self.beats)

    def snapshot(self) -> dict:
        return {
            "kind": self.kind, "world_start": self.world_start,
            "start_ms": self.start_at * 1000.0, "beats": self.beats,
            "spans": [[s.beats, s.start_bpm, s.end_bpm] for s in self.spans],
            "take_id": self.take_id, "mode": self.mode,
            "source_from_beat": self.source_from_beat,
            "meter": list(self.meter),
        }


def take_spans(tempo_segments, from_beat: float, end_beat: float,
               bpm: float) -> tuple[TempoSpan, ...]:
    """Constant spans of a source tempo map (start, end, bpm), local to
    from_beat..end_beat. Beats outside the map keep the nearest tempo."""
    spans = []
    cursor = float(from_beat)
    rate = float(bpm)
    for start, end, value in sorted(tempo_segments or ()):
        start, end, value = float(start), float(end), float(value)
        if end <= cursor + 1e-9:
            rate = value
            continue
        if start >= end_beat - 1e-9:
            break
        if start > cursor + 1e-9:
            spans.append(TempoSpan(start - cursor, rate, rate))
            cursor = start
        stop = min(end, end_beat)
        spans.append(TempoSpan(stop - cursor, value, value))
        cursor, rate = stop, value
    if cursor < end_beat - 1e-9:
        spans.append(TempoSpan(end_beat - cursor, rate, rate))
    return tuple(spans) or (TempoSpan(0.0, bpm, bpm),)


def rest_to_barline(sounding_end: float, barlines) -> float:
    """Beats from a take's last sounding note to the barline at or after it.

    `barlines` are the take's measure boundaries in its own source beats;
    past the last one the final bar length repeats.
    """
    lines = sorted(float(x) for x in barlines)
    for line in lines:
        if line >= sounding_end - 1e-7:
            return max(0.0, line - sounding_end)
    if len(lines) < 2:
        return 0.0
    bar = lines[-1] - lines[-2]
    if bar <= 0:
        return 0.0
    bars = math.ceil((sounding_end - lines[-1]) / bar - 1e-7)
    return max(0.0, lines[-1] + bars * bar - sounding_end)


@dataclass(frozen=True, slots=True)
class TakeSpec:
    """A take to place: its source opening, tempo and the rest after it."""
    take_id: str
    mode: str
    source_from_beat: float
    spans: tuple[TempoSpan, ...]
    rest_after_beats: float = 0.0


class MusicalTimeline:
    def __init__(self):
        self.run = 0
        self.segments: list[TimelineSegment] = []
        # (wall start, duration or None while the pause lasts)
        self.holds: list[tuple[float, float | None]] = []
        # A closed run holds its world here; nothing follows yet.
        self.end_world: float | None = None

    # --- clock ---------------------------------------------------------

    def reset(self) -> None:
        self.run += 1
        self.segments = []
        self.holds = []
        self.end_world = None

    def close(self) -> None:
        """Hold the world after the last take's rest to its barline."""
        last = self.last_take()
        if last is not None and self.end_world is None:
            self.end_world = last.world_end + last.rest_after_beats

    @property
    def open(self) -> bool:
        """A run is moving and the next take may follow it."""
        return bool(self.segments) and self.end_world is None

    @property
    def paused(self) -> bool:
        return bool(self.holds) and self.holds[-1][1] is None

    def musical(self, t: float) -> float:
        """Musical seconds at wall instant `t`."""
        m = t
        for at, duration in self.holds:
            if t > at:
                m -= min(t - at, math.inf if duration is None else duration)
        return m

    def wall(self, m: float) -> float:
        """Earliest wall instant at musical time `m` (inf inside an open pause)."""
        t = m
        for at, duration in self.holds:
            if m > self.musical(at):
                if duration is None:
                    return math.inf
                t += duration
        return t

    def pause(self, t: float) -> None:
        if self.segments and not self.paused:
            self.holds.append((t, None))

    def resume(self, t: float) -> None:
        if self.paused:
            at, _ = self.holds[-1]
            self.holds[-1] = (at, max(0.0, t - at))

    # --- evaluation ----------------------------------------------------

    def _segment_at(self, m: float) -> TimelineSegment:
        chosen = self.segments[0]
        for segment in self.segments:
            if segment.start_at > m:
                break
            chosen = segment
        return chosen

    def world_at(self, t: float) -> float | None:
        """World beat at wall instant `t`; past the last segment the
        music continues as an open rest at its final tempo."""
        world = self._world_at(t)
        if world is not None and self.end_world is not None:
            return min(world, self.end_world)
        return world

    def _world_at(self, t: float) -> float | None:
        if not self.segments:
            return None
        m = self.musical(t)
        first = self.segments[0]
        if m <= first.start_at:
            return first.world_start
        segment = self._segment_at(m)
        if m >= segment.end_at and segment is self.segments[-1]:
            return segment.world_end + (m - segment.end_at) * segment.end_bpm / 60.0
        return segment.world_start + segment.beat_at(m - segment.start_at)

    def musical_at_world(self, world: float) -> float | None:
        """Musical seconds at which the timeline reaches `world`."""
        if not self.segments:
            return None
        first = self.segments[0]
        if world <= first.world_start:
            return first.start_at
        chosen = first
        for segment in self.segments:
            if segment.world_start > world:
                break
            chosen = segment
        if world >= chosen.world_end and chosen is self.segments[-1]:
            return chosen.end_at + (world - chosen.world_end) * 60.0 / chosen.end_bpm
        return chosen.start_at + chosen.seconds_at(world - chosen.world_start)

    def time_at(self, world: float) -> float | None:
        m = self.musical_at_world(world)
        return None if m is None else self.wall(m)

    def last_take(self) -> TimelineSegment | None:
        return next((s for s in reversed(self.segments) if s.kind == "take"), None)

    def take(self, take_id: str) -> TimelineSegment | None:
        if not take_id:
            return None
        return next((s for s in self.segments
                     if s.kind == "take" and s.take_id == take_id), None)

    def segment_at(self, t: float) -> TimelineSegment | None:
        return self._segment_at(self.musical(t)) if self.segments else None

    def take_start(self, take: TimelineSegment) -> float:
        """Wall instant of a take's first beat."""
        return self.wall(take.start_at)

    # --- placement -----------------------------------------------------

    def append(self, segment: TimelineSegment) -> TimelineSegment:
        if self.segments:
            last = self.segments[-1]
            if (abs(segment.world_start - last.world_end) > 1e-6
                    or abs(segment.start_at - last.end_at) > 1e-6):
                raise ValueError("Timeline segments must be contiguous")
        self.segments.append(segment)
        return segment

    def _append_take(self, take: TakeSpec, *, world: float, at: float) -> TimelineSegment:
        return self.append(TimelineSegment(
            "take", world, at, take.spans, take_id=take.take_id,
            mode=take.mode, source_from_beat=take.source_from_beat,
            rest_after_beats=take.rest_after_beats))

    def planned_count_in_start(self) -> float | None:
        """Musical seconds of the next count-in by bar arithmetic alone."""
        if not self.segments or self.segments[-1].kind != "take":
            return None
        last = self.segments[-1]
        return last.end_at + last.rest_after_beats * 60.0 / last.end_bpm

    def continue_after_take(self, take: TakeSpec, *, now: float,
                            bar_beats: float, meter: tuple[int, int],
                            bpm: float, grace: float = LATE_GRACE_SECONDS
                            ) -> TimelineSegment:
        """Rest to the barline, one count-in bar, then `take`.

        A decision that arrives after the count-in should have started adds
        whole rest bars at the outgoing tempo, never an error.
        """
        last = self.segments[-1] if self.segments else None
        if last is None or last.kind != "take":
            raise ValueError("A continuation follows a take")
        outgoing = last.end_bpm
        rest = last.rest_after_beats
        floor = self.musical(now) - grace
        while last.end_at + rest * 60.0 / outgoing < floor:
            rest += bar_beats
        if rest > 1e-9:
            self.append(TimelineSegment(
                "rest", last.world_end, last.end_at,
                (TempoSpan(rest, outgoing, outgoing),)))
        tail = self.segments[-1]
        count_in = self.append(TimelineSegment(
            "count_in", tail.world_end, tail.end_at,
            count_in_spans(bar_beats, outgoing, bpm), meter=tuple(meter)))
        return self._append_take(take, world=count_in.world_end, at=count_in.end_at)

    def start_after(self, take: TakeSpec, *, now: float, rest_beats: float,
                    bar_beats: float, meter: tuple[int, int], bpm: float,
                    lead: float = RUN_LEAD_SECONDS) -> TimelineSegment:
        """Rest past `rest_beats` of ink still ahead of the playhead, one
        count-in bar, then `take`. Continues the run after a cut take;
        otherwise begins it at `now`."""
        self.end_world = None
        m = self.musical(now)
        if self.segments:
            last = self.segments[-1]
            world, at, tempo = last.world_end, last.end_at, last.end_bpm
        else:
            world, at, tempo = 0.0, m, bpm
        rest = max(0.0, rest_beats)
        # Never start the count-in before the state can reach Godot.
        rest = max(rest, (m + lead - at) * tempo / 60.0)
        if rest > 1e-9:
            world = self.append(TimelineSegment(
                "rest", world, at, (TempoSpan(rest, tempo, tempo),))).world_end
            at = self.segments[-1].end_at
        count_in = self.append(TimelineSegment(
            "count_in", world, at, count_in_spans(bar_beats, tempo, bpm),
            meter=tuple(meter)))
        return self._append_take(take, world=count_in.world_end, at=count_in.end_at)

    def cut_take(self, t: float) -> None:
        """End the current take at wall instant `t` (Resume continues it in a
        new take after its own count-in)."""
        if not self.segments or self.segments[-1].kind != "take":
            return
        last = self.segments[-1]
        beats = last.beat_at(self.musical(t) - last.start_at)
        self.segments[-1] = replace(last, cut_beats=beats)

    # --- publication ---------------------------------------------------

    def snapshot(self, now: float) -> dict | None:
        if not self.segments:
            return None
        m = self.musical(now)
        past = [i for i, s in enumerate(self.segments) if s.end_at < m]
        first = max(0, (past[-1] + 1 - KEPT_PAST_SEGMENTS) if past else 0)
        return {
            "run": self.run,
            "end_world": self.end_world,
            "holds_ms": [[at * 1000.0, None if d is None else d * 1000.0]
                         for at, d in self.holds],
            "segments": [s.snapshot() for s in self.segments[first:]],
        }

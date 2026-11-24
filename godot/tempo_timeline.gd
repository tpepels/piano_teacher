extends RefCounted

# Canonical signed unit conversions for all Godot presentation consumers.
# This does not decide graded deadlines (the Python MusicalScheduler does).
# Signed values are deliberate: an upcoming countdown is before beat zero.
static func seconds_from_beats(beats: float, bpm: float) -> float:
    return beats * 60.0 / bpm

static func beats_from_seconds(seconds: float, bpm: float) -> float:
    return seconds * bpm / 60.0

static func beats_from_milliseconds(milliseconds: float, bpm: float) -> float:
    return beats_from_seconds(milliseconds / 1000.0, bpm)

# Exactly one piecewise-constant mapping for source beats and WAV seconds.
# Segments are the same local-zero TempoMap.as_segments values supplied by
# the Python practice engine to engraving transport, grading and Listen.
# The count-in precedes zero and keeps the selected preparation BPM.
static func seconds_at_beat(beat: float, nominal_bpm: float, segments: Array) -> float:
    var nominal: float = maxf(1.0, nominal_bpm)
    if segments.is_empty() or beat <= 0.0:
        return seconds_from_beats(beat, nominal)
    var elapsed := 0.0
    var final_beat := 0.0
    var final_bpm := nominal
    for raw in segments:
        var segment: Dictionary = raw
        var first: float = float(segment.get("start_beat", final_beat))
        var last: float = float(segment.get("end_beat", first))
        var speed: float = maxf(1.0, float(segment.get("bpm", nominal)))
        if beat <= first:
            return elapsed
        elapsed += seconds_from_beats(minf(beat, last) - first, speed)
        final_beat = last
        final_bpm = speed
        if beat <= last:
            return elapsed
    return elapsed + seconds_from_beats(beat - final_beat, final_bpm)


# Current source velocity. Keep the perpetual score stream faithful to
# authored variable tempo while its position remains independent of seeks.
static func bpm_at_beat(beat: float, nominal_bpm: float,
        segments: Array) -> float:
    var selected: float = maxf(1.0, nominal_bpm)
    if beat < 0.0 or segments.is_empty():
        return selected
    for raw in segments:
        var segment: Dictionary = raw
        var start: float = float(segment.get("start_beat",0.0))
        var end: float = float(segment.get("end_beat",start))
        var speed: float = maxf(1.0,float(segment.get("bpm",selected)))
        if beat < start:
            return selected
        selected = speed
        if beat < end:
            return selected
    return selected


extends RefCounted

# Exactly one piecewise-constant mapping for source beats and WAV seconds.
# Segments are the same local-zero TempoMap.as_segments values supplied by
# the Python practice engine to engraving transport, grading and Listen.
# The count-in precedes zero and keeps the selected preparation BPM.
static func seconds_at_beat(beat: float, nominal_bpm: float, segments: Array) -> float:
    var nominal: float = maxf(1.0, nominal_bpm)
    if segments.is_empty() or beat <= 0.0:
        return beat * 60.0 / nominal
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
        elapsed += (minf(beat, last) - first) * 60.0 / speed
        final_beat = last
        final_bpm = speed
        if beat <= last:
            return elapsed
    return elapsed + (beat - final_beat) * 60.0 / final_bpm


static func beat_at_seconds(seconds: float, nominal_bpm: float, segments: Array) -> float:
    var nominal: float = maxf(1.0, nominal_bpm)
    if segments.is_empty() or seconds <= 0.0:
        return seconds * nominal / 60.0
    var elapsed := 0.0
    var final_beat := 0.0
    var final_bpm := nominal
    for raw in segments:
        var segment: Dictionary = raw
        var first: float = float(segment.get("start_beat", final_beat))
        var last: float = float(segment.get("end_beat", first))
        var speed: float = maxf(1.0, float(segment.get("bpm", nominal)))
        var until: float = elapsed + (last - first) * 60.0 / speed
        if seconds <= until:
            return first + (seconds - elapsed) * speed / 60.0
        elapsed = until
        final_beat = last
        final_bpm = speed
    return final_beat + (seconds - elapsed) * final_bpm / 60.0

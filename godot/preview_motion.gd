extends RefCounted

# Preview-only constant velocity over an already engraved piece. All normal
# MIDI-assessed practice and Listen follow exact Verovio attack positions.
# The preview does not grade or synthesize per-note arrival timestamps.
static func pixels_per_beat(points: Array) -> float:
    if points.size() < 2:
        return 0.0
    var first: Dictionary = points[0]
    var start: float = float(first.get("beat", 0.0))
    for index in range(points.size() - 1, 0, -1):
        var last: Dictionary = points[index]
        var beats: float = float(last.get("beat", 0.0)) - start
        var pixels: float = float(last.get("x", 0.0)) - float(first.get("x", 0.0))
        if beats > .00001 and pixels > 0.0:
            return pixels / beats
    return 0.0

static func position(points: Array, beat: float) -> float:
    if points.is_empty():
        return 0.0
    return float(points[0].get("x", 0.0)) + (
        beat - float(points[0].get("beat", 0.0))) * pixels_per_beat(points)

extends RefCounted
## Position a stopped, already-engraved source at its first available attack
## when the selected passage begins with silence beyond the visible horizon.
## Never changes clock beats, MIDI grading, tempo maps or the source timeline.
static func beat_for_ready(events: Array, hand: String, start_beat: float,
        width: float, pixels_per_beat: float, playhead_fraction: float) -> float:
    if pixels_per_beat <= 0.0 or width <= 0.0:
        return start_beat
    var first := INF
    for event in events:
        if str(event.get("kind","")) != "note":
            continue
        var staff: String = str(event.get("staff","right"))
        if hand != "both" and staff != hand:
            continue
        var at: float = float(event.get("beat",INF))
        if at >= start_beat-0.00001:
            first = minf(first,at)
    if not is_finite(first):
        return start_beat
    var ahead: float = width*(1.0-playhead_fraction)/pixels_per_beat
    if first <= start_beat+ahead*.88:
        return start_beat
    # The next note should be clearly visible with ample forward room.
    # The original leading rest remains in the authentic score, and Play
    # uses the original start_beat, not this display-only projection.
    return maxf(start_beat,first-maxf(.25,ahead*.45))

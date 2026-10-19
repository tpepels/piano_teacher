extends RefCounted
# Phase 1: an exact, clock-locked camera over *real Verovio ink*.
#
# Do not guess where a note is. Only activate when the already engraved
# glyph anchors prove that source x = origin + beat * pixels_per_beat.
# The renderer may use Verovio's original noteheads, beams, stems, ties,
# ornaments and accidentals; none are redrawn or stretched by this class.
#
# This is an intentionally narrow initial adapter. Unsupported layouts keep
# the existing cursor-following camera until a glyph-group renderer handles
# their non-proportional engraving safely.

const TOLERANCE_SOURCE_PX := 2.0
const MIN_DISTINCT_BEATS := 3

static func prepare(layout: Dictionary) -> Dictionary:
    if not bool(layout.get("strip_time_proportional", false)):
        return {"enabled": false, "reason": "Verovio layout has not been aligned to a beat grid"}
    var fallback: String = str(layout.get("strip_timing_fallback", ""))
    if not fallback.is_empty():
        return {"enabled": false, "reason": fallback}
    var widths: Array = layout.get("widths", [])
    if widths.is_empty() or float(widths[0]) <= 0.0:
        return {"enabled": false, "reason": "Missing engraved strip width"}
    var width: float = float(widths[0])
    var ordered: Array = layout.get("anchors", []).duplicate(true)
    ordered.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        return float(a.get("beat", 0.0)) < float(b.get("beat", 0.0)))
    var distinct: Array[Vector2] = []
    for anchor in ordered:
        if int(anchor.get("page", -1)) != 0:
            return {"enabled": false, "reason": "Multiple visible engraved pages"}
        var beat: float = float(anchor.get("beat", -INF))
        var x: float = float(anchor.get("x", -INF)) * width
        if not is_finite(beat) or not is_finite(x):
            return {"enabled": false, "reason": "Non-finite source beat or engraved position"}
        if not distinct.is_empty() and absf(beat - distinct[-1].x) <= .000001:
            if absf(x - distinct[-1].y) > TOLERANCE_SOURCE_PX:
                return {"enabled": false,
                    "reason": "Simultaneous Verovio notes disagree about horizontal position"}
            continue
        distinct.append(Vector2(beat, x))
    if distinct.size() < MIN_DISTINCT_BEATS:
        return {"enabled": false, "reason": "Insufficient measured rhythmic anchors"}
    var first: Vector2 = distinct[0]
    var last: Vector2 = distinct[-1]
    var span: float = last.x - first.x
    if span <= .000001:
        return {"enabled": false, "reason": "Empty musical beat span"}
    var slope: float = (last.y - first.y) / span
    if not is_finite(slope) or slope <= 0.0:
        return {"enabled": false, "reason": "Invalid Verovio pixels per beat"}
    var origin: float = first.y - first.x * slope
    var maximum_error := 0.0
    for point in distinct:
        var error: float = absf(point.y - (origin + point.x * slope))
        maximum_error = maxf(maximum_error, error)
        if maximum_error > TOLERANCE_SOURCE_PX:
            return {"enabled": false, "reason": "Engraving is not uniformly beat-spaced",
                "max_error_px": maximum_error, "pixels_per_beat": slope}
    return {"enabled": true, "origin_px": origin, "pixels_per_beat": slope,
        "max_error_px": maximum_error, "measured_beats": distinct.size()}


# The score moves, not the playhead. An authoritative Python clock-beat is
# relative to play_from_beat, including negative beats before the start.
# Paused playback passes the same clock and therefore yields the same x.
static func camera_x(grid: Dictionary, clock_beat: float, play_from_beat: float,
        fixed_playhead_x: float, view_scale: float) -> float:
    var score_beat: float = play_from_beat + clock_beat
    var logical: float = float(grid.get("origin_px", 0.0)) + score_beat * float(
        grid.get("pixels_per_beat", 0.0))
    return fixed_playhead_x - logical * view_scale

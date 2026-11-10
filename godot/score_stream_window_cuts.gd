extends RefCounted
## One immutable clip boundary for each *unconnected* visual ink unit.
## Source beats, note timing and renderer world origins never move. A strip
## boundary may shift within adjacent blank pixel space, but it must not cut
## through a source glyph or a crossing Verovio beam/tie/slur/tuplet/hairpin.
## When no clear seam exists, merge the two adjoining source strips; such a
## connected visual unit is indivisible during maximal safe suffix removal.
const SEAM_CLEARANCE_PIXELS := 1.5
const MAX_SHIFT_BEATS := .5

static func _merged(ink: Array[Vector2]) -> Array[Vector2]:
    var sorted: Array[Vector2] = ink.duplicate()
    sorted.sort_custom(func(a: Vector2,b: Vector2) -> bool:
        return a.x < b.x)
    var output: Array[Vector2] = []
    for raw in sorted:
        if not is_finite(raw.x) or not is_finite(raw.y) or raw.y <= raw.x:
            continue
        if not output.is_empty() and raw.x <= output[-1].y:
            var merged: Vector2 = output[-1]
            merged.y = maxf(merged.y,raw.y)
            output[-1] = merged
        else:
            output.append(raw)
    return output

static func safe_windows(opening: float, duration: float,
        measures: Array, ink: Array[Vector2],
        max_shift: float = MAX_SHIFT_BEATS) -> Array[Vector2]:
    var result: Array[Vector2] = []
    if not is_finite(opening) or not is_finite(duration) or opening >= duration:
        return result
    var cuts: Array[float] = [opening]
    for measure in measures:
        var at: float = float(measure.get("start_beat",-INF))
        if at > opening+.00001 and at < duration-.00001:
            cuts.append(at)
    cuts.append(duration)
    cuts.sort()
    var obstacles: Array[Vector2] = _merged(ink)
    var chosen: Array[float] = [opening]
    var cursor := 0
    for index in range(1,cuts.size()-1):
        var center: float = cuts[index]
        # Binary/monotone scan: each obstacle is passed at most once for
        # an entire score, instead of scanning thousands of notes per bar.
        while cursor < obstacles.size() and obstacles[cursor].y < center:
            cursor += 1
        var seam: float = center
        if cursor < obstacles.size() and obstacles[cursor].x <= center and \
                obstacles[cursor].y >= center:
            var blocked: Vector2 = obstacles[cursor]
            var near_left: float = blocked.x-.0001
            var near_right: float = blocked.y+.0001
            var left_ok: bool = center-near_left <= max_shift and \
                near_left > chosen[-1]+.0001
            var right_ok: bool = near_right-center <= max_shift and \
                near_right < cuts[index+1]-.0001
            if left_ok and (not right_ok or \
                    center-near_left <= near_right-center):
                seam = near_left
            elif right_ok:
                seam = near_right
            else:
                # The ink physically connects both measures: admitting
                # them as separately withdrawable clips would cut it.
                continue
        if seam <= chosen[-1]+.0001 or seam >= duration-.0001:
            continue
        chosen.append(seam)
    chosen.append(duration)
    for index in range(chosen.size()-1):
        if chosen[index+1] > chosen[index]+.00001:
            result.append(Vector2(chosen[index],chosen[index+1]))
    return result

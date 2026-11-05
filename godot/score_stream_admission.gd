extends RefCounted
## Single, source-bounded admission policy for an endless forward-only staff.
## Python still owns MIDI deadlines, assessment, retry and lesson progression.
## A paused take freezes its visible source horizon; already admitted ink keeps
## travelling left. A resume cannot expose the same upcoming source interval
## twice while its earlier copy is still ahead of the playhead.
const LOOKAHEAD_BEATS := 3.5
const FUTURE_GUARD_BEATS := 0.04

static func window(source: float, opening: float, duration: float,
        reserved_until: float = -INF) -> Dictionary:
    if not is_finite(source) or not is_finite(opening) or not is_finite(duration):
        return {"admit": false, "floor": 0.0, "ceiling": 0.0}
    var floor: float = maxf(maxf(0.0, opening), source + FUTURE_GUARD_BEATS)
    if is_finite(reserved_until):
        floor = maxf(floor, reserved_until)
    var ceiling: float = minf(duration, source + LOOKAHEAD_BEATS)
    return {"admit": ceiling > floor + .0001,
        "floor": floor, "ceiling": ceiling}

static func reserved_through(passes: Array, take_key: String, world: float) -> float:
    var limit := -INF
    for item in passes:
        if str(item.get("take_key", "")) != take_key:
            continue
        var end_world: float = float(item.get("world_origin", 0.0)) + \
            float(item.get("source_ceiling", 0.0))
        # Source material that has passed the playhead can be re-presented;
        # upcoming material is owned by its original, still-moving clip.
        if end_world > world + FUTURE_GUARD_BEATS:
            limit = maxf(limit, float(item.get("source_ceiling", 0.0)))
    return limit

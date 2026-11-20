extends RefCounted
## Read-only contour clearance at the single fixed playhead. Immutable
## source strips and canonical events determine only vertical mask gaps.
## This helper cannot paint, authorize, withdraw or move a score strip.

static func exclusions(world: float, gap: float, density: float,
        events: Array, stream_snapshot: Array, layout,
        active_hand: String) -> Array:
    var intervals: Array = []
    if events.is_empty():
        return intervals
    var guard: float = gap*1.7/density
    for item in stream_snapshot:
        if str(item.get("kind","source")) != "source":
            continue
        var source_beat: float = world-float(item["world_origin"])
        if source_beat+guard < float(item["source_floor"]) or \
                source_beat-guard > float(item["source_ceiling"]):
            continue
        var lo := 0
        var hi: int = events.size()
        while lo < hi:
            var mid: int = (lo+hi)>>1
            if float(events[mid].get("beat",0.0)) < source_beat-guard:
                lo = mid+1
            else:
                hi = mid
        for index in range(lo,events.size()):
            var event: Dictionary = events[index]
            var at: float = float(event.get("beat",0.0))
            if at > source_beat+guard:
                break
            if absf((at-source_beat)*density) > gap*1.5:
                continue
            var kind: String = str(event.get("kind",""))
            if kind not in ["note","rest"]:
                continue
            var staff: String = str(event.get("staff","right"))
            if active_hand not in ["both",staff]:
                continue
            var y: float = (layout.rest_y(event,gap) if kind=="rest"
                else layout.event_y(event,gap))
            var half: float = gap*(1.8 if kind=="rest" else 1.1)
            intervals.append(Vector2(y-half,y+half))
    intervals.sort_custom(func(a: Vector2,b: Vector2) -> bool:
        return a.x < b.x)
    return intervals

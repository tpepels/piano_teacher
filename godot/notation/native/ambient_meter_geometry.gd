extends RefCounted
## Sole read-only calculation for the moving barlines between printed strips.
## No renderer painter or queue mutation is permitted in this helper.
const Grid := preload("res://moving_meter_grid.gd")
const Admission := preload("res://score_stream_admission.gd")

static func exposed_lines(world: float, width: float, playhead: float,
        density: float, gap: float, duration: float,
        authored_measures: Array, prior_anchor: float,
        stream_snapshot: Array) -> Dictionary:
    var anchor: float = prior_anchor
    for item in stream_snapshot:
        if str(item.get("kind","")) == "source":
            anchor = float(item["world_origin"])
            break
    var positions: Array[float] = []
    var world_bars: Array[float] = Grid.visible_lines(
        world,width,playhead,density,anchor,authored_measures)
    # The online ledger is ordered by printed left edge, just as the
    # retained-score projection expects. Compute visible coverage once,
    # rather than recomputing the entire queue for every ambient barline.
    var coverage: Array[Vector2] = []
    for item in stream_snapshot:
        var source_left: float = playhead+(
            float(item["world_origin"])-world)*density
        var bounds: Vector2 = Admission.clip_bounds(item,density,gap,duration)
        var interval := Vector2(source_left+bounds.x-.01,
            source_left+bounds.y+.01)
        if interval.x > width+.01:
            break
        if interval.y >= -.01:
            coverage.append(interval)
    for bar_world in world_bars:
        var x: float = playhead+(bar_world-world)*density
        var covered := false
        for interval in coverage:
            if interval.x > x:
                break
            if x <= interval.y:
                covered = true
                break
        if not covered:
            positions.append(x)
    return {"anchor":anchor,"positions":positions}

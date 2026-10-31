extends RefCounted
## Pure spatial projection of retained source notehead metadata.
## Note locations are sorted by source X at engraving time. Each transport
## frame reads only visible notes, never traverses the entire score.

static func append_visible(notes: Array, shift_x: float, viewport_width: float,
        playhead_x: float, pass_index: int,
        instances: Array, nearest_heads: Dictionary) -> int:
    var minimum: float = -60.0-shift_x
    var maximum: float = viewport_width+60.0-shift_x
    var low := 0
    var high: int = notes.size()
    while low < high:
        var midpoint: int = (low+high)>>1
        if float(notes[midpoint]["position"].x) < minimum:
            low = midpoint+1
        else:
            high = midpoint
    var count := 0
    for index in range(low,notes.size()):
        var original: Dictionary = notes[index]
        var point: Vector2 = original["position"]
        if point.x > maximum:
            break
        var screen: Vector2 = point+Vector2(shift_x,0.0)
        var ident: String = str(original["event_id"])
        var copy: Dictionary = original.duplicate(false)
        copy["position"] = screen
        copy["pass_index"] = pass_index
        copy["instance_id"] = "%d:%s" % [pass_index,ident]
        instances.append(copy)
        if not nearest_heads.has(ident) or \
                absf(screen.x-playhead_x)<absf(nearest_heads[ident].x-playhead_x):
            nearest_heads[ident] = screen
        count += 1
    return count

extends RefCounted
## Source-meter-accurate blank-staff barline locations. The axis is the same
## immutable continuous world coordinate as every retained source/rest strip.
## Only visible world beats are returned; a long imported score never causes
## per-frame whole-piece scanning or guessed uniform meter subdivisions.

static func visible_lines(world: float, width: float, playhead_x: float,
        density: float, origin: float, measures: Array,
        fallback_beats: float = 4.0) -> Array[float]:
    var scale: float = maxf(1.0,density)
    var left: float = world-playhead_x/scale
    var right: float = world+(width-playhead_x)/scale
    var lines: Array[float] = []
    if not is_finite(origin):
        origin = 0.0
    var effective: Array = measures
    if effective.is_empty():
        effective = [{"start_beat":0.0,"end_beat":maxf(.25,fallback_beats)}]
    var first: Dictionary = effective[0]
    var last: Dictionary = effective[-1]
    var first_start: float = float(first.get("start_beat",0.0))
    var last_end: float = float(last.get("end_beat",4.0))
    var first_width: float = maxf(.25,
        float(first.get("end_beat",first_start+fallback_beats))-first_start)
    var last_width: float = maxf(.25,last_end-float(last.get("start_beat",0.0)))
    # An initial pickup must retain the next authored boundary, while the
    # preparation before it follows the opening written meter. Forward
    # extensions after the score use the final written meter, not 4/4.
    var first_world: float = origin+first_start
    var repeat_before: int = maxi(0,ceili((first_world-left)/first_width))
    for i in range(mini(80,repeat_before+1)):
        var at: float = first_world-float(i)*first_width
        if at >= left-.00001 and at <= right+.00001:
            lines.append(at)
    # The source grid can contain thousands of measures. Binary-search
    # its sorted starts and examine only the few that cross this viewport.
    var target_first: float = left-origin-.00001
    var lo := 0
    var hi: int = effective.size()
    while lo < hi:
        var middle: int = (lo+hi)>>1
        if float(effective[middle].get("start_beat",0.0)) < target_first:
            lo = middle+1
        else:
            hi = middle
    for index in range(lo,effective.size()):
        var at: float = origin+float(effective[index].get("start_beat",0.0))
        if at > right+.00001:
            break
        lines.append(at)
    var end_world: float = origin+last_end
    if end_world >= left-.00001 and end_world <= right+.00001:
        lines.append(end_world)
    var repeat_after: int = maxi(0,ceili((right-end_world)/last_width))
    for i in range(1,mini(81,repeat_after+1)):
        var at: float = end_world+float(i)*last_width
        if at >= left-.00001 and at <= right+.00001:
            lines.append(at)
    lines.sort()
    var unique: Array[float] = []
    for at in lines:
        if unique.is_empty() or absf(at-unique[-1]) > .00001:
            unique.append(at)
    return unique

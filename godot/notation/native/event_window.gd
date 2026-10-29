extends RefCounted

# Bounded, binary-searched event selection for one native render pass.
# Leaves all source/loop visibility rules in the passed RenderPass.
static func visible(events: Array, left: float, right: float, frame) -> Array:
    var begin := 0
    var end: int = events.size()
    while begin < end:
        var middle: int = (begin + end) >> 1
        if float(events[middle].get("beat", 0.0)) < left-.25:
            begin = middle + 1
        else:
            end = middle
    var results: Array = []
    for index in range(begin, events.size()):
        var event: Dictionary = events[index]
        if float(event.get("beat", 0.0)) > right+.25:
            break
        if frame.event_visible(event):
            results.append(event)
    return results

extends RefCounted
## Stateless source-copy visibility during practice recovery.

static func event_visible(event: Dictionary, pass_start: float, loop: bool, history: Dictionary) -> bool:
    if not loop:
        return true
    var at: float = pass_start+float(event.get("beat",event.get("start_beat",0.0)))
    for preparation in history.values():
        var silence: Dictionary = preparation["measure"]
        if at>=float(silence["start_beat"])-.00001 and at<float(silence["end_beat"])-.00001:
            return false
    return true


static func span_visible(first: Dictionary, last: Dictionary,
        pass_start: float, loop: bool, history: Dictionary) -> bool:
    if not loop:
        return true
    for preparation in history.values():
        var silence: Dictionary = preparation["measure"]
        if pass_start+float(last["beat"])>=float(silence["start_beat"])-.00001 and \
                pass_start+float(first["beat"])<float(silence["end_beat"])-.00001:
            return false
    return true


static func intervals_overlap(first: Dictionary, second: Dictionary) -> bool:
    return float(first["start_beat"])<float(second["end_beat"])-.00001 and \
        float(second["start_beat"])<float(first["end_beat"])-.00001

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

## Recover the preceding source measure, including the copy-boundary gap.
## Pure: never mutates source measure dictionaries or preparation history.
static func practice_context_before(at: float, stride: float,
        measures: Array, ordinary_gap: Dictionary) -> Dictionary:
    if at <= .00001:
        return {}
    var pass_start: float = maxf(0.0, floorf(at / stride)) * stride
    var local: float = at - pass_start
    var previous: Dictionary = {}
    for measure in measures:
        if float(measure["start_beat"]) < local - .00001:
            previous = measure
    if previous.is_empty() and pass_start > 0.0:
        var incoming: Dictionary = ordinary_gap.duplicate(true)
        incoming["start_beat"] = pass_start - float(incoming["duration_beats"])
        incoming["end_beat"] = pass_start
        return incoming
    if previous.is_empty():
        return {}
    var result: Dictionary = previous.duplicate(true)
    result["start_beat"] = float(result["start_beat"]) + pass_start
    result["end_beat"] = float(result["end_beat"]) + pass_start
    return result

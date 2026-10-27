extends RefCounted
# Stateless musical-ink spacing policy. The caller supplies authentic positioned
# ink from the engraving engine; no rendering, camera or tempo state enters here.
# A single returned density applies to the ENTIRE loaded exercise.

static func minimum_density(items: Array, preferred: float, gap: float) -> Dictionary:
    var staves: Dictionary = {"right":{}, "left":{}}
    var minimum_left := INF
    var maximum_right := -INF
    for item in items:
        var staff: String = str(item["staff"])
        var beat: float = float(item["beat"])
        var ink: Rect2 = item["ink"]
        if not staves.has(staff):
            staves[staff] = {}
        if not staves[staff].has(beat):
            staves[staff][beat] = []
        staves[staff][beat].append(item)
        minimum_left = minf(minimum_left,ink.position.x)
        maximum_right = maxf(maximum_right,ink.end.x)
    var density: float = preferred
    var witness: Dictionary = {"reason":"configured-density",
        "required_density":preferred,"staff_gap":gap}
    var reach: float = (maximum_right-minimum_left+gap*.2)/preferred
    for staff in staves:
        var onsets: Array = staves[staff].keys()
        onsets.sort()
        for i in range(1,onsets.size()):
            for j in range(i-1,-1,-1):
                var distance: float = float(onsets[i])-float(onsets[j])
                if distance > reach:
                    break
                for previous_item in staves[staff][onsets[j]]:
                    for current_item in staves[staff][onsets[i]]:
                        var previous: Rect2 = previous_item["ink"]
                        var current: Rect2 = current_item["ink"]
                        # Notes in separate vertical registers cannot collide.
                        if current.position.y >= previous.end.y+gap*.1 or \
                                previous.position.y >= current.end.y+gap*.1:
                            continue
                        var necessary: float = (previous.end.x-current.position.x+
                            gap*.2)/distance
                        if necessary > density:
                            density = necessary
                            var prev_event: Dictionary = previous_item["event"]
                            var next_event: Dictionary = current_item["event"]
                            witness = {
                                "reason":"horizontal-ink-clearance",
                                "required_density":necessary,
                                "staff_gap":gap,
                                "previous_id":str(prev_event.get("id","")),
                                "next_id":str(next_event.get("id","")),
                                "previous_kind":str(prev_event.get("kind","")),
                                "next_kind":str(next_event.get("kind","")),
                                "previous_type":str(prev_event.get("note_type","")),
                                "next_type":str(next_event.get("note_type","")),
                                "previous_voice":str(prev_event.get("voice","")),
                                "next_voice":str(next_event.get("voice","")),
                                "previous_pitch":str(prev_event.get("spelling",{})),
                                "next_pitch":str(next_event.get("spelling",{})),
                                "previous_beat":float(onsets[j]),
                                "next_beat":float(onsets[i]),
                                "beat_separation":distance,
                                "previous_rect":[previous.position.x,
                                    previous.position.y,previous.size.x,previous.size.y],
                                "next_rect":[current.position.x,
                                    current.position.y,current.size.x,current.size.y]
                            }
    return {"density":density, "witness":witness}

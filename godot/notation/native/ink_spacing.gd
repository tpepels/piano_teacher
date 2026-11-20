extends RefCounted
# Stateless musical-ink spacing policy. The caller supplies authentic positioned
# ink from the engraving engine; no rendering, camera or tempo state enters here.
# A single returned density applies to the ENTIRE loaded exercise.


# Single owner of horizontal attack-readability policy. The authentic
# glyph collision solver below may demand more space than these preferences.
const MIN_SOURCE_ATTACK_SPACING_PX := 25.0
const SIXTEENTH_STAFF_SPACES := 3.3


static func source_attack_intervals_fit(events: Array, max_density: float) -> bool:
    # Reject unrepresentable distinct attacks, not prescribe a second scale.
    # Extremely close source clocks in ONE staff/voice cannot be separated
    # on a fixed linear axis even at MAX_SCORE_PIXELS_PER_BEAT. Different
    # voices/registers and simultaneous chord members do not falsely collide.
    # Actual spacing and staff-scale fitting belong to minimum_density().
    if not is_finite(max_density) or max_density <= 0.0:
        return false
    var lanes: Dictionary = {}
    for event in events:
        if not event is Dictionary or str(event.get("kind","")) != "note":
            continue
        var clock: float = float(event.get("beat",NAN))
        if not is_finite(clock):
            return false
        var lane: String = str(event.get("staff",""))+"|"+str(event.get("voice","1"))
        if not lanes.has(lane):
            lanes[lane] = []
        lanes[lane].append(clock)
    for lane in lanes:
        var beats: Array = lanes[lane]
        beats.sort()
        for index in range(1,beats.size()):
            var distance: float = float(beats[index])-float(beats[index-1])
            if distance > .00001 and distance*max_density < MIN_SOURCE_ATTACK_SPACING_PX:
                return false
    return true


# Readability floor beyond exact ink collision prevention. A sequence of 16th
# note attacks needs more than 24px at the former 96px/beat, even when glyph
# contours technically do not overlap. Avoid treating a single rolled/grace
# MIDI attack as a dense passage. Return a whole-score linear density; do not
# retime events, move individual noteheads or distort notation.
static func readable_density(notes: Array, preferred: float, gap: float = 22.0) -> float:
    # A linear axis guarantees every sixteenth 3.3 spaces whenever genuine
    # eighth-or-faster source content is present, including a single figure.
    var beats: Array[float] = []
    for note in notes:
        if not note is Dictionary:
            continue
        if float(note.get("duration_beats",INF)) <= .5+.000001:
            return maxf(preferred,SIXTEENTH_STAFF_SPACES*gap/.25)
        beats.append(float(note.get("onset_beats",INF)))
    beats.sort()
    for index in range(1,beats.size()):
        var distance: float = beats[index]-beats[index-1]
        if distance > .000001 and distance <= .5+.000001:
            return maxf(preferred,SIXTEENTH_STAFF_SPACES*gap/.25)
    return preferred

static func minimum_density(items: Array, preferred: float, gap: float,
        boundaries: Array = []) -> Dictionary:
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
    var outgoing: Dictionary = outgoing_boundary_density(items,boundaries,density,gap)
    if float(outgoing["density"]) > density:
        density = float(outgoing["density"])
        witness = outgoing["witness"]
    var incoming: Dictionary = incoming_boundary_density(items,boundaries,density,gap)
    return incoming if float(incoming["density"]) > density else {"density":density,"witness":witness}


static func outgoing_boundary_density(items: Array, boundaries: Array,
        preferred: float, gap: float) -> Dictionary:
    # Boundary ink is positioned relative to its musical beat, including the
    # common engraving lead and every stroke's actual width/offset. Glyph
    # bands exclude connectors that may intentionally cross a barline.
    var density: float = preferred
    var witness: Dictionary = {}
    var ordered: Array = items.duplicate()
    ordered.sort_custom(func(a: Dictionary,b: Dictionary) -> bool: return float(a["beat"]) < float(b["beat"]))
    var furthest := -INF
    for item in ordered:
        for band in item.get("boundary_ink",[item["ink"]]):
            furthest = maxf(furthest,band.end.x)
    for boundary in boundaries:
        var beat: float = float(boundary["beat"])
        var stroke: Rect2 = boundary["ink"]
        var reach: float = (furthest-stroke.position.x+gap*.2)/preferred
        var begin := 0
        var end := ordered.size()
        while begin < end:
            var middle: int = (begin+end) >> 1
            if float(ordered[middle]["beat"]) < beat:
                begin = middle+1
            else:
                end = middle
        for index in range(begin-1,-1,-1):
            var item: Dictionary = ordered[index]
            var distance: float = beat-float(item["beat"])
            if distance > reach:
                break
            # Equality is deliberately excluded above: density cannot move
            # a same-clock courtesy accidental relative to its boundary.
            for band in item.get("boundary_ink",[item["ink"]]):
                if band.position.y >= stroke.end.y or band.end.y <= stroke.position.y:
                    continue
                var required: float = (band.end.x-stroke.position.x+(gap*.45 + 6.0))/distance
                if required > density:
                    density = required
                    witness = {"reason":"outgoing-barline-clearance","required_density":required,
                        "staff_gap":gap,"previous_id":str(item.get("event",{}).get("id","")),
                        "previous_beat":float(item["beat"]),"boundary_beat":beat,
                        "beat_separation":distance,"glyph_right":band.end.x,
                        "stroke_left":stroke.position.x}
    return {"density":density,"witness":witness}


static func incoming_boundary_density(items: Array, boundaries: Array,
        preferred: float, gap: float) -> Dictionary:
    # A barline must also have readable clearance to its first following
    # attack. Preserve the musical onset; alter only uniform px-per-beat.
    var density := preferred
    var witness: Dictionary = {}
    var ordered: Array = items.duplicate()
    ordered.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        return float(a["beat"]) < float(b["beat"]))
    for boundary in boundaries:
        var beat: float = float(boundary["beat"])
        var stroke: Rect2 = boundary["ink"]
        for item in ordered:
            var distance: float = float(item["beat"])-beat
            if distance <= 0.000001:
                continue
            if distance*density > gap*8.0:
                break
            for band in item.get("boundary_ink", [item["ink"]]):
                if band.position.y >= stroke.end.y or band.end.y <= stroke.position.y:
                    continue
                var needed: float = (stroke.end.x-band.position.x+
                    maxf(9.0, gap*.45)) / distance
                if needed > density:
                    density = needed
                    witness = {"reason":"incoming-barline-clearance",
                        "required_density":needed, "staff_gap":gap,
                        "next_id":str(item.get("event", {}).get("id", "")),
                        "boundary_beat":beat, "next_beat":float(item["beat"]),
                        "beat_separation":distance}
    return {"density":density,"witness":witness}

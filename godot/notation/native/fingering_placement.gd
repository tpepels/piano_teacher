extends RefCounted
## Local candidate origins for the existing native annotation compositor.
## All distances are staff spaces; no candidate changes musical geometry.

static func candidates(head: Vector2, ink: Vector2, gap: float,
        direction: float, chord: bool, stem_up: bool, staff_center: float,
        hint: Dictionary = {}) -> Array:
    var result: Array = []
    var preferred := -1.0 if hint.get("placement","") == "above" else 1.0 if hint.get("placement","") == "below" else direction
    var preferred_side := -1.0 if stem_up else 1.0
    var offsets: Array = []
    if hint.has("default_y"):
        var x: float = head.x-ink.x*.5+float(hint.get("default_x",0.0))*gap/10.0
        var y: float = staff_center-gap*2.0-float(hint["default_y"])*gap/10.0-ink.y
        offsets.append({"position":Vector2(x,y),"orientation":"authored"})
    # Chord fingers form a small column beside their individual tones. A
    # second column accommodates seconds; it never stacks all chord digits
    # above/below the chord's outermost note.
    if chord:
        for side in [preferred_side,-preferred_side]:
            for distance in [.95,1.65]:
                var x: float = head.x+float(side)*gap*float(distance)-(ink.x if float(side)<0 else 0.0)
                for dy in [0.0,-.18,.18]:
                    offsets.append({"position":Vector2(x,head.y-ink.y*.5+float(dy)*gap),"orientation":"side"})
    # Ordinary notes first try a close placement in the hand/voice direction.
    # Local alternatives clear stems and ledger lines without a remote lane.
    for direction_y in [preferred]:
        for distance in [.2,.4,.6,.9,1.2,1.5,1.8]:
            for dx in [0.0,-.65,.65,-1.05,1.05]:
                var y: float = head.y+float(direction_y)*gap*float(distance)-(ink.y if float(direction_y)<0 else 0.0)
                offsets.append({"position":Vector2(head.x-ink.x*.5+float(dx)*gap,y),
                    "orientation":"above" if float(direction_y)<0 else "below"})
    if not chord:
        for side in [preferred_side,-preferred_side]:
            for distance in [.95,1.4,1.65]:
                for dy in [-.4,.4,0.0]:
                    offsets.append({"position":Vector2(head.x+float(side)*gap*float(distance)-(ink.x if float(side)<0 else 0.0),
                        head.y-ink.y*.5+float(dy)*gap),"orientation":"side"})
    # The opposite side of the note is a last resort, after local lateral
    # choices have been exhausted. Voice/explicit placement wins the default.
    for distance in [.2,.4,.6,.9,1.2,1.5,1.8]:
        for dx in [0.0,-.65,.65,-1.05,1.05]:
            var y: float = head.y-preferred*gap*float(distance)-(ink.y if preferred>0 else 0.0)
            offsets.append({"position":Vector2(head.x-ink.x*.5+float(dx)*gap,y),
                "orientation":"above" if preferred>0 else "below"})
    var adjustment := Vector2(float(hint.get("relative_x",0.0)),-float(hint.get("relative_y",0.0)))*gap/10.0
    if hint.has("default_x") and not hint.has("default_y"):
        adjustment.x += float(hint["default_x"])*gap/10.0
    if adjustment.length()>gap*1.25:
        adjustment = Vector2.ZERO
    for candidate in offsets:
        var point: Vector2 = candidate["position"]+adjustment
        if absf(point.y+ink.y*.5-staff_center)<=gap*2.5:
            var snapped: Vector2 = point
            var top: float = staff_center-gap*2.0
            snapped.y = top+gap*.5+roundf((point.y+ink.y*.5-top-gap*.5)/gap)*gap-ink.y*.5
            if (snapped+ink*.5).distance_to(head)<=gap*2.45:
                result.append({"position":snapped,"orientation":candidate["orientation"]})
        var center: Vector2 = point+ink*.5
        if center.distance_to(head) <= gap*2.45 and absf(center.x-head.x) <= gap*2.0:
            result.append({"position":point,"orientation":candidate["orientation"]})
    return result


static func fallback_candidates(head: Vector2, ink: Vector2, gap: float,
        direction: float, stem_up: bool) -> Array:
    # Only used after the musical preferences fail. Search the SAME bounded
    # neighborhood more finely; sparse preferred offsets must not hide a
    # valid narrow space between a ledger, chord tone and staff rule.
    var offsets: Array = []
    for y in range(-24,25):
        for x in range(-20,21):
            var offset := Vector2(x,y)*.1
            if offset.length()<.7 or offset.length()>2.45:
                continue
            offsets.append(offset)
    var side: float = -1.0 if stem_up else 1.0
    offsets.sort_custom(func(a: Vector2,b: Vector2) -> bool:
        var cost_a: float = a.length()+(0.1 if a.y*direction<0.0 else 0.0)
        var cost_b: float = b.length()+(0.1 if b.y*direction<0.0 else 0.0)
        if absf(cost_a-cost_b)>.000001:
            return cost_a<cost_b
        if absf(a.y-b.y)>.000001:
            return a.y*direction>b.y*direction
        return a.x*side>b.x*side)
    var result: Array = []
    for offset in offsets:
        result.append({"position":head+offset*gap-ink*.5,
            "orientation":"above" if offset.y<-.7 else "below" if offset.y>.7 else "side"})
    return result


static func assignment(event: Dictionary) -> Dictionary:
    if str(event.get("kind", "")) != "note" or not bool(event.get("is_attack", false)):
        return {}
    var value: Variant = event.get("fingering")
    if not value is Dictionary:
        return {}
    var finger: Variant = value.get("finger")
    if typeof(finger) not in [TYPE_INT, TYPE_FLOAT] or \
            not is_finite(float(finger)) or float(finger) != floorf(float(finger)) or \
            int(finger) < 1 or int(finger) > 5:
        return {}
    if value.get("hand") not in ["left", "right"] or \
            not value.get("source_id") is String or str(value["source_id"]).is_empty() or \
            value.get("origin") not in ["manual", "authored", "automatic"]:
        return {}
    return value


static func source(event: Dictionary) -> String:
    var assignment: Variant = event.get("fingering")
    if assignment is Dictionary and assignment.get("source_id") is String:
        return assignment["source_id"]
    var source: Variant = event.get("source_id")
    return source if source is String else ""

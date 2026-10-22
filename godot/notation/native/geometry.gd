extends RefCounted
# Deterministic engraving-independent geometry for Phase C.
# No texture, Verovio resource, frame clock or audio timing dependency.
const STEPS := {"C":0, "D":1, "E":2, "F":3, "G":4, "A":5, "B":6}
const SUPPORTED := ["whole", "half", "quarter", "eighth", "16th", "32nd", "64th", "128th"]
const BARLINE_STYLES := ["regular", "light-light", "light-heavy",
    "heavy-light", "heavy-heavy", "heavy", "none", "dashed", "dotted",
    "tick", "short"]
const NOTE_BEATS := {"whole":4.0,"half":2.0,"quarter":1.0,
    "eighth":.5,"16th":.25,"32nd":.125,"64th":.0625,"128th":.03125}

static func dotted_multiplier(dots: int) -> float:
    var result := 1.0
    var fraction := .5
    for ignored in range(dots):
        result += fraction
        fraction *= .5
    return result

static func valid_modification(event: Dictionary) -> bool:
    var modification: Variant = event.get("time_modification")
    if modification == null:
        return true
    if not modification is Dictionary:
        return false
    var actual: int = int(modification.get("actual", 0))
    var normal: int = int(modification.get("normal", 0))
    if actual <= 0 or normal <= 0 or actual > 10080 or normal > 10080:
        return false
    var named: String = str(event.get("note_type", ""))
    var dots: int = int(event.get("dots", 0))
    var expected: float = float(NOTE_BEATS.get(named, 0.0)) * \
        dotted_multiplier(dots) * float(normal)/float(actual)
    return absf(expected-float(event.get("duration_beats", -1.0))) < .0003

const HEAD_HALF_WIDTH := 9.2
const MIN_ATTACK_SEPARATION := 25.0
const ACCIDENTAL_GLYPHS := {"sharp":"acc_sharp","flat":"acc_flat",
    "natural":"acc_natural","double-sharp":"acc_double_sharp",
    "double-flat":"acc_double_flat","flat-flat":"acc_double_flat"}

static func diatonic_index(spelling: Dictionary) -> int:
    var name: String = str(spelling.get("step", ""))
    if not STEPS.has(name):
        return -9999
    return int(spelling.get("octave", 4)) * 7 + int(STEPS[name])

static func bottom_line(clef: Dictionary) -> int:
    var sign: String = str(clef.get("sign", "G"))
    var line: int = int(clef.get("line", 2))
    var octave_change: int = int(clef.get("octave_change", 0))
    var base: int = 4*7+4 if sign == "G" else 3*7+3 if sign == "F" else 4*7
    # G clef encircles G4 on its declared line; F encircles F3;
    # C clef locates C4. Octave-clef shift is measured in diatonic steps.
    return base - (line-1)*2 + octave_change*7

static func staff_step(spelling: Dictionary, clef: Dictionary) -> int:
    return diatonic_index(spelling) - bottom_line(clef)

static func note_y(step: int, bottom_y: float, gap: float) -> float:
    return bottom_y - float(step)*gap*.5

# SMuFL/Leipzig rest origin is a staff-line reference, not the visual
# centre of its bounding box. A whole rest hangs FROM line 4; a half rest
# rests ON line 3. Other rest glyphs use the staff's middle line.
static func rest_staff_offset(note_type: String) -> float:
    return -1.0 if note_type == "whole" else 0.0

# Dots sit beside the rest's ink: below the hanging whole-rest line, above
# the half-rest support line. This is relative to the same glyph origin.
static func rest_dot_offset(note_type: String) -> float:
    return .5 if note_type == "whole" else 0.0

static func supported(model: Dictionary) -> String:
    if not model.get("unrendered_expressions", []).is_empty():
        return "Source expression requires original Verovio engraving"
    if not model.has("notation_events") or not model["notation_events"] is Array:
        return "Semantic score has no notation events"
    var events: Array = model["notation_events"]
    var notes_seen: Dictionary = {}
    for event in events:
        if not event is Dictionary:
            return "Invalid symbol"
        var kind: String = str(event.get("kind", ""))
        var duration: String = str(event.get("note_type", ""))
        if kind not in ["note", "rest"] or duration not in SUPPORTED:
            return "Unsupported music value: " + duration
        if int(event.get("dots", 0)) < 0 or int(event.get("dots", 0)) > 4:
            return "More than four rhythm dots are not supported"
        if not valid_modification(event):
            return "Invalid or unrepresentable tuplet time ratio"
        for mark in event.get("tuplet_marks", []):
            if not mark is Dictionary or str(mark.get("type", "")) \
                    not in ["start", "stop"]:
                return "Unsupported tuplet grouping marker"
        if kind == "note":
            if not event.get("spelling") is Dictionary or \
                    diatonic_index(event["spelling"]) < 0:
                return "Unknown note spelling"
            var key: String = str(event.get("id", ""))
            if key.is_empty() or notes_seen.has(key):
                return "Missing or duplicate notation note identity"
            notes_seen[key] = true
        if str(event.get("staff", "")) not in ["right", "left"]:
            return "Unsupported staff"
    var previous_right: Variant = null
    for measure in model.get("measures", []):
        if not measure is Dictionary:
            return "Invalid measure"
        var opening: Variant = measure.get("left_barline")
        if previous_right is Dictionary and opening is Dictionary:
            var old_style: String = str(previous_right.get("style","regular"))
            var old_repeat: String = str(previous_right.get("repeat",""))
            var new_repeat: String = str(opening.get("repeat",""))
            var paired: bool = old_repeat == "backward" and \
                new_repeat == "forward"
            if not paired and old_style not in ["regular","none"] and \
                    opening != previous_right:
                return "Conflicting source barline styles at one measure boundary"
        previous_right = measure.get("right_barline")
        for side in ["left_barline","right_barline"]:
            var descriptor: Variant = measure.get(side)
            if descriptor == null:
                continue
            if not descriptor is Dictionary or \
                    str(descriptor.get("style","")) not in BARLINE_STYLES or \
                    str(descriptor.get("repeat","")) not in ["","forward","backward"]:
                return "Unsupported source barline descriptor"
        var clefs: Dictionary = measure.get("clefs", {})
        for hand in ["right", "left"]:
            var clef: Dictionary = clefs.get(hand, {})
            if str(clef.get("sign", "G" if hand == "right" else "F")) \
                    not in ["G", "F", "C"]:
                return "Unimplemented clef"
            if abs(int(clef.get("octave_change", 0))) > 1:
                return "Unimplemented octave clef"
            if str(clef.get("sign", "")) == "C" and \
                    int(clef.get("octave_change",0)) > 0:
                return "Source C-clef octave-above glyph unavailable in installed Verovio font"
            if abs(int(measure.get("keys", {}).get(hand, 0))) > 7:
                return "Invalid key signature"
    return ""

static func required_density(events: Array, preferred: float,
        limit: float = 480.0) -> float:
    # Establish ONE density for the entire exercise before animation.
    # Adjacent source onsets on the same staff must have room for heads
    # and accidental ink. Never change the density per note or mid-scroll.
    var voices: Dictionary = {}
    for event in events:
        if not event is Dictionary:
            continue
        if str(event.get("kind", "")) != "note":
            continue
        var key: String = str(event.get("staff", "")) + "|" + \
            str(event.get("voice", "1"))
        if not voices.has(key):
            voices[key] = []
        voices[key].append(float(event.get("beat", 0.0)))
    var minimum_gap := INF
    for key in voices:
        var onsets: Array = voices[key]
        onsets.sort()
        for index in range(1, onsets.size()):
            var distance: float = float(onsets[index])-float(onsets[index-1])
            if distance > .00001:
                minimum_gap = minf(minimum_gap, distance)
    var needed := preferred
    # A fixed 25 px spacing is sufficient for tiny 64ths but far too
    # cramped for ordinary quarter/eighth reading on a large grand staff.
    # Choose one score-wide density from each successive source onset:
    # source beat positions and camera speed remain perfectly linear.
    for key in voices:
        var onsets: Array = voices[key]
        onsets.sort()
        for index in range(1, onsets.size()):
            var distance: float = float(onsets[index])-float(onsets[index-1])
            if distance <= .00001:
                continue  # Simultaneous chord notes share one musical attack.
            var readable: float = (MIN_ATTACK_SEPARATION if
                distance <= .0625001 else
                minf(96.0, maxf(MIN_ATTACK_SEPARATION,
                    78.0*sqrt(distance/.5))))
            needed = maxf(needed, readable/distance)
    return needed if needed <= limit else -1.0

static func event_positions(model: Dictionary, density: float) -> Dictionary:
    # Used for regression audits and for notehead feedback in Phase D.
    var result: Dictionary = {}
    for event in model.get("notation_events", []):
        if event is Dictionary:
            result[str(event.get("id", ""))] = float(event.get("beat", 0.0))*density
    return result


# Beam membership and stem direction come from source engraving metadata
# in score_index.gd; geometry must not infer alternate groups from meter.
static func beamed_ids(groups: Array) -> Dictionary:
    var lookup: Dictionary = {}
    for group in groups:
        for event in group:
            lookup[str(event.get("id", ""))] = true
    return lookup

# Key signatures use the circle-of-fifths order. Their steps are measured
# against each clef, never repeated at one arbitrary y like a text label.
static func signature_steps(clef: Dictionary, fifths: int) -> Array:
    var sharps: Array = [
        {"step":"F","octave":5}, {"step":"C","octave":5},
        {"step":"G","octave":5}, {"step":"D","octave":5},
        {"step":"A","octave":4}, {"step":"E","octave":5},
        {"step":"B","octave":4}]
    var flats: Array = [
        {"step":"B","octave":4}, {"step":"E","octave":5},
        {"step":"A","octave":4}, {"step":"D","octave":5},
        {"step":"G","octave":4}, {"step":"C","octave":5},
        {"step":"F","octave":4}]
    var pitches: Array = sharps if fifths > 0 else flats
    var result: Array = []
    for i in range(mini(7, absi(fifths))):
        var written: Dictionary = pitches[i].duplicate()
        var step: int = staff_step(written, clef)
        # Shift each symbol by octaves to live near the staff. This
        # preserves correct letter placement across G/F/C clefs.
        while step > 10:
            step -= 7
        while step < 0:
            step += 7
        result.append(step)
    return result

static func key_cancellation_steps(clef: Dictionary, before: int,
        after: int) -> Array:
    # An old key has to relinquish accidentals when the signature
    # switches direction, shrinks or returns to C major/A minor.
    # Retain accidentals shared by signatures of the same sign.
    if before == 0 or before == after:
        return []
    if (before > 0) == (after > 0) and after != 0 and \
            absi(after) >= absi(before):
        return []
    var old_steps: Array = signature_steps(clef, before)
    if before * after < 0 or after == 0:
        return old_steps
    return old_steps.slice(mini(old_steps.size(), absi(after)))


static func chord_members(events: Array) -> Dictionary:
    # A MusicXML chord has exactly one unmarked onset followed by notes with
    # chord=true at the SAME beat, staff and voice. Keep the entire pitch range
    # associated with that leader; only the leader may draw its shared stem.
    var lanes: Dictionary = {}
    for event in events:
        if not event is Dictionary or str(event.get("kind", "")) != "note":
            continue
        var key: String = str(event.get("staff", ""))+"|"+ \
            str(event.get("voice", "1"))+"|"+ \
            str(event.get("measure", 0))+"|"+ \
            str(snappedf(float(event.get("beat", 0.0)), .000001))
        if not lanes.has(key):
            lanes[key] = []
        lanes[key].append(event)
    var result: Dictionary = {}
    for key in lanes:
        var notes: Array = lanes[key]
        if notes.size() < 2:
            continue
        var leader: Dictionary = {}
        for note in notes:
            if not bool(note.get("chord", false)):
                leader = note
                break
        if not leader.is_empty():
            result[str(leader.get("id", ""))] = notes
    return result


static func chord_offsets(events: Array, gap: float) -> Dictionary:
    # Engraved unisons/seconds must never be placed on top of each other.
    # This is a glyph-only horizontal offset: the musical beat and scroll
    # camera remain untouched. Alternating sides centres the whole chord.
    var lanes: Dictionary = {}
    for event in events:
        if not event is Dictionary or str(event.get("kind", "")) != "note":
            continue
        var name: String = str(event.get("staff",""))+"|"+ \
            str(event.get("voice","1"))+"|"+str(event.get("measure",0))+"|"+ \
            str(snappedf(float(event.get("beat", 0.0)), .000001))
        if not lanes.has(name):
            lanes[name] = []
        lanes[name].append(event)
    var result: Dictionary = {}
    for key in lanes:
        var chord: Array = lanes[key]
        if chord.size() < 2:
            continue
        chord.sort_custom(func(a,b):
            return diatonic_index(a.get("spelling",{})) < \
                diatonic_index(b.get("spelling",{})))
        for i in range(1,chord.size()):
            var previous: int = diatonic_index(chord[i-1].get("spelling",{}))
            var current: int = diatonic_index(chord[i].get("spelling",{}))
            if current-previous == 1:
                # Alternate each close neighbour, avoid sustained drift
                # when three or more adjacent pitches form a cluster.
                var old_id: String = str(chord[i-1].get("id",""))
                var new_id: String = str(chord[i].get("id",""))
                var old_offset: float = float(result.get(old_id,0.0))
                var width: float = gap*.75
                if absf(old_offset) < .001:
                    result[old_id] = -width
                    result[new_id] = width
                else:
                    result[new_id] = -old_offset
    return result


static func accidental_offsets(events: Array, gap: float,
        head_offsets: Dictionary, glyph_bounds: Dictionary) -> Dictionary:
    # Pack authentic glyph bounding boxes once per staff/onset. A single
    # fixed left offset makes accidentals on seconds/thirds overprint each
    # other. Include all voices sharing a staff; leave musical X unchanged.
    var lanes: Dictionary = {}
    for event in events:
        if str(event.get("kind","")) != "note":
            continue
        var key: String = str(event.get("staff",""))+"|"+ \
            str(event.get("measure",0))+"|"+ \
            str(snappedf(float(event.get("beat",0.0)),.000001))
        if not lanes.has(key):
            lanes[key] = []
        lanes[key].append(event)
    var result: Dictionary = {}
    var unit: float = gap/250.0
    for key in lanes:
        var accidentals: Array = []
        var left_edge := INF
        for event in lanes[key]:
            var id: String = str(event.get("id",""))
            var head_x: float = float(head_offsets.get(id,0.0))
            var kind: String = str(event.get("note_type","quarter"))
            var head: Array = glyph_bounds.get("head_"+(
                kind if kind in ["whole","half"] else "black"),[])
            if head.size() == 4:
                left_edge = minf(left_edge,head_x-float(head[2])*unit*.5)
            var name: String = str(ACCIDENTAL_GLYPHS.get(
                str(event.get("accidental","")),""))
            var box: Array = glyph_bounds.get(name,[])
            if box.size() != 4:
                continue
            var y: float = -float(diatonic_index(event.get("spelling",{})))*gap*.5
            accidentals.append({"id":id,"head_x":head_x,
                "top":y+float(box[1])*unit,
                "bottom":y+(float(box[1])+float(box[3]))*unit,
                "width":float(box[2])*unit})
        if accidentals.is_empty() or not is_finite(left_edge):
            continue
        accidentals.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            if absf(float(a["top"])-float(b["top"])) > .001:
                return float(a["top"]) < float(b["top"])
            return str(a["id"]) < str(b["id"]))
        var columns: Array = []
        for accidental in accidentals:
            var selected := -1
            for i in range(columns.size()):
                var clear := true
                for other in columns[i]["items"]:
                    if float(accidental["top"]) < float(other["bottom"])+gap*.15 and \
                            float(accidental["bottom"]) > float(other["top"])-gap*.15:
                        clear = false
                        break
                if clear:
                    selected = i
                    break
            if selected < 0:
                selected = columns.size()
                columns.append({"width":0.0,"items":[]})
            columns[selected]["width"] = maxf(float(columns[selected]["width"]),
                float(accidental["width"]))
            columns[selected]["items"].append(accidental)
        var right: float = left_edge-gap*.25
        for column in columns:
            for accidental in column["items"]:
                result[str(accidental["id"])] = right- \
                    float(accidental["width"])*.5-float(accidental["head_x"])
            right -= float(column["width"])+gap*.2
    return result


static func tuplet_groups(model: Dictionary) -> Array:
    # Group from explicit MusicXML start/stop, not from guessed X intervals.
    # An unusual standalone time-modification is displayed with its
    # full actual:normal ratio instead of being silently misrepresented.
    var lanes: Dictionary = {}
    for event in model.get("notation_events", []):
        if not event is Dictionary:
            continue
        var key: String = str(event.get("staff", "")) + "|" + \
            str(event.get("voice", "1")) + "|" + \
            str(event.get("measure", 0))
        if not lanes.has(key):
            lanes[key] = []
        if not bool(event.get("chord", false)):
            lanes[key].append(event)
    var groups: Array = []
    for key in lanes:
        var events: Array = lanes[key]
        events.sort_custom(func(a,b): return float(a.get("beat", 0.0)) < \
            float(b.get("beat", 0.0)))
        var opened: Dictionary = {}
        for event in events:
            var marks: Array = event.get("tuplet_marks", [])
            var modifier: Variant = event.get("time_modification")
            for mark in marks:
                if str(mark.get("type", "")) == "start":
                    var number: String = str(mark.get("number", "1"))
                    opened[number] = {
                        "events": [], "staff":event.get("staff", "right"),
                        "actual":int(modifier.get("actual", 1)) if modifier is Dictionary else 1,
                        "normal":int(modifier.get("normal", 1)) if modifier is Dictionary else 1,
                        "bracket":str(mark.get("bracket", "yes")),
                        "show_number":str(mark.get("show_number", "actual"))
                    }
            var attached := false
            if modifier is Dictionary:
                for number in opened:
                    var group: Dictionary = opened[number]
                    if group["actual"] == int(modifier.get("actual", 0)) \
                            and group["normal"] == int(modifier.get("normal", 0)):
                        group["events"].append(event)
                        attached = true
                if not attached:
                    groups.append({"events":[event],
                        "staff":event.get("staff", "right"),
                        "actual":int(modifier.get("actual", 1)),
                        "normal":int(modifier.get("normal", 1)),
                        "bracket":"yes", "show_number":"ratio"})
            for mark in marks:
                if str(mark.get("type", "")) == "stop":
                    var number: String = str(mark.get("number", "1"))
                    if opened.has(number):
                        groups.append(opened[number])
                        opened.erase(number)
        # An unclosed group is not emitted as a misleading bracket.
    return groups

static func tuplet_label(group: Dictionary) -> String:
    var actual: int = int(group.get("actual", 1))
    var normal: int = int(group.get("normal", 1))
    var presentation: String = str(group.get("show_number", "actual"))
    if presentation == "ratio" or presentation == "both":
        return "%d:%d" % [actual, normal]
    if presentation == "none":
        # Show the numeric ratio anyway for ad-hoc source durations:
        # a bare bracket cannot explain an unconventional rhythm.
        return "%d:%d" % [actual, normal]
    return str(actual)

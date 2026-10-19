extends RefCounted
# Deterministic engraving-independent geometry for Phase C.
# No texture, Verovio resource, frame clock or audio timing dependency.
const STEPS := {"C":0, "D":1, "E":2, "F":3, "G":4, "A":5, "B":6}
const SUPPORTED := ["whole", "half", "quarter", "eighth", "16th", "32nd", "64th"]
const BEAM_LEVELS := {"eighth":1, "16th":2, "32nd":3, "64th":4}
const BARLINE_STYLES := ["regular", "light-light", "light-heavy",
    "heavy-light", "heavy-heavy", "heavy", "none", "dashed", "dotted"]
const NOTE_BEATS := {"whole":4.0,"half":2.0,"quarter":1.0,
    "eighth":.5,"16th":.25,"32nd":.125,"64th":.0625}

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

static func beam_level(note_type: String) -> int:
    return int(BEAM_LEVELS.get(note_type, 0))
const HEAD_HALF_WIDTH := 9.2
const MIN_ATTACK_SEPARATION := 25.0

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

static func supported(model: Dictionary) -> String:
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
        if int(event.get("dots", 0)) < 0 or int(event.get("dots", 0)) > 2:
            return "More than two rhythm dots are not supported"
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
    if is_finite(minimum_gap):
        needed = maxf(needed, MIN_ATTACK_SEPARATION/minimum_gap)
    return needed if needed <= limit else -1.0

static func event_positions(model: Dictionary, density: float) -> Dictionary:
    # Used for regression audits and for notehead feedback in Phase D.
    var result: Dictionary = {}
    for event in model.get("notation_events", []):
        if event is Dictionary:
            result[str(event.get("id", ""))] = float(event.get("beat", 0.0))*density
    return result


# C2: conventional beaming is a semantic grouping, never a scroll operation.
# Only group unambiguous beats: ordinary meters by quarter beat and 6/8,
# 9/8, 12/8 by dotted-quarter beat. Ambiguous irregular meters leave flags.
static func beat_group_length(meter: Array) -> float:
    if meter.size() < 2:
        return 0.0
    var numerator: int = int(meter[0])
    var denominator: int = int(meter[1])
    if denominator == 8 and numerator in [3, 6, 9, 12]:
        return 1.5
    if denominator == 2 and numerator in [2, 3, 4]:
        return 2.0
    if denominator == 4 and numerator in [2, 3, 4]:
        return 1.0
    if denominator == 8 and numerator in [2, 4]:
        return 1.0
    if denominator == 16 and numerator in [2, 4]:
        return .5
    return 0.0

static func _beam_finish(group: Array, output: Array) -> void:
    if group.size() >= 2:
        output.append(group.duplicate())

static func beam_groups(model: Dictionary) -> Array:
    # Sequence by staff, voice and bar. Rests, unbeamable durations, ties
    # and gaps break groups; chord tones share the leader's beam/stem.
    var lanes: Dictionary = {}
    var measures: Dictionary = {}
    for measure in model.get("measures", []):
        if measure is Dictionary:
            measures[int(measure.get("number", 0))] = measure
    for event in model.get("notation_events", []):
        if not event is Dictionary:
            continue
        var staff: String = str(event.get("staff", ""))
        var voice: String = str(event.get("voice", "1"))
        var number: int = int(event.get("measure", 0))
        var key: String = staff + "|" + voice + "|" + str(number)
        if not lanes.has(key):
            lanes[key] = {"measure":number, "events":[]}
        if bool(event.get("chord", false)):
            continue
        lanes[key]["events"].append(event)
    var tuplet_membership: Dictionary = {}
    var serial := 0
    for group in tuplet_groups(model):
        var events: Array = group.get("events", [])
        if events.size() >= 2:
            for event in events:
                tuplet_membership[str(event.get("id", ""))] = serial
            serial += 1
    var output: Array = []
    for key in lanes:
        var measure: Dictionary = measures.get(int(lanes[key]["measure"]), {})
        var length: float = beat_group_length(measure.get("meter", []))
        var conventional_grouping: bool = length > 0.0
        if length <= 0.0:
            # Even an irregular meter can contain an explicitly grouped
            # MusicXML tuplet. Do not guess beams for its other notes.
            length = 1.0
        var ordered: Array = lanes[key]["events"]
        ordered.sort_custom(func(a, b): return float(a["beat"]) < float(b["beat"]))
        var current: Array = []
        var current_group := ""
        var previous_end := -INF
        var begin: float = float(measure.get("start_beat", 0.0))
        for event in ordered:
            var at: float = float(event.get("beat", -1.0))
            var duration: float = float(event.get("duration_beats", 0.0))
            var short: bool = str(event.get("kind", "")) == "note" and \
                beam_level(str(event.get("note_type", ""))) > 0 and \
                duration > 0.0 and duration <= .75 and \
                (conventional_grouping or tuplet_membership.has(
                    str(event.get("id", ""))))
            var unit: int = int(floor((at-begin+.000001)/length))
            # Notes may end on the next group boundary but not cross it.
            var stays: bool = at+duration <= begin+float(unit+1)*length+.00001
            var grouping: String = ("tuplet:" + str(tuplet_membership[
                str(event.get("id", ""))]) if tuplet_membership.has(
                str(event.get("id", ""))) else "meter:" + str(unit))
            if grouping.begins_with("tuplet:"):
                stays = true
            var consecutive: bool = absf(at-previous_end) <= .0001
            if not short or not stays or (not current.is_empty() and \
                    (grouping != current_group or not consecutive)):
                _beam_finish(current, output)
                current = []
            if short and stays:
                current.append(event)
                current_group = grouping
                previous_end = at+duration
            else:
                previous_end = -INF
        _beam_finish(current, output)
    return output

static func beamed_ids(groups: Array) -> Dictionary:
    var lookup: Dictionary = {}
    for group in groups:
        for event in group:
            lookup[str(event.get("id", ""))] = true
    return lookup

static func stem_up(group: Array, model: Dictionary) -> bool:
    if group.is_empty():
        return true
    var measure_by_number: Dictionary = {}
    for measure in model.get("measures", []):
        measure_by_number[int(measure.get("number", 0))] = measure
    var total := 0.0
    for event in group:
        var m: Dictionary = measure_by_number.get(int(event.get("measure", 0)), {})
        var clef: Dictionary = m.get("clefs", {}).get(str(event.get("staff", "right")), {})
        total += float(staff_step(event.get("spelling", {}), clef))
    return total/float(group.size()) < 4.0


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

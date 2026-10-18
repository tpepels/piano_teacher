extends RefCounted
# Deterministic engraving-independent geometry for Phase C.
# No texture, Verovio resource, frame clock or audio timing dependency.
const STEPS := {"C":0, "D":1, "E":2, "F":3, "G":4, "A":5, "B":6}
const SUPPORTED := ["whole", "half", "quarter", "eighth", "16th"]
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
        if int(event.get("dots", 0)) > 1 or event.get("time_modification") != null:
            return "Tuplets and double-dotted rhythms require Verovio fallback"
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
    for measure in model.get("measures", []):
        if not measure is Dictionary:
            return "Invalid measure"
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

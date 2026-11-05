extends RefCounted
## One collision-free future reservation policy for the perpetual practice bar.
## A passage owns a finite global-time interval. Pause freezes admissions;
## retry and resume may create new intervals only after all older visible ink.
## The backend retains the authority over MIDI assessment and run_at deadlines.
const LOOKAHEAD_BEATS := 3.5
const FUTURE_GUARD_BEATS := 1.0
const REST_GAP_BEATS := 0.65
const MAX_READING_SECONDS := 30.0

static func furthest_occupied_world(passes: Array, now: float) -> float:
    var furthest := -INF
    for item in passes:
        var finish: float = float(item.get("world_origin",0.0)) + \
            float(item.get("source_ceiling",0.0))
        if is_finite(finish) and finish > now:
            furthest = maxf(furthest,finish)
    return furthest

static func next_safe_world(passes: Array, world: float) -> float:
    var earliest: float = world + FUTURE_GUARD_BEATS
    var occupied: float = furthest_occupied_world(passes,world)
    if is_finite(occupied):
        earliest = maxf(earliest,occupied+REST_GAP_BEATS)
    return earliest

static func reading_lead_seconds(passes: Array, world: float, bpm: float) -> float:
    # UI informs the authoritative engine how far ahead its next deadline
    # must lie to avoid the not-yet-departed score, including reading time.
    var beats: float = maxf(LOOKAHEAD_BEATS,
        next_safe_world(passes,world)-world)
    return minf(MAX_READING_SECONDS,beats*60.0/maxf(1.0,bpm))

static func window(source: float, opening: float, duration: float,
        world: float, passes: Array = []) -> Dictionary:
    if not is_finite(source) or not is_finite(opening) or \
            not is_finite(duration) or not is_finite(world):
        return {"admit":false, "floor":0.0, "ceiling":0.0}
    # Each unmodified retained source copy uses origin = world - source.
    # Do not create a clip over other pending ink, and never place its
    # earliest note on/behind the playhead.
    var origin: float = world-source
    var floor: float = maxf(maxf(0.0,opening),
        next_safe_world(passes,world)-origin)
    var ceiling: float = minf(duration,source+LOOKAHEAD_BEATS)
    return {"admit":ceiling > floor+.0001,
        "floor":floor, "ceiling":ceiling}

static func collision_pairs(passes: Array, notes: Array,
        world: float, pixels_per_beat: float, tolerance_px: float = 12.0) -> Array:
    # The same-pitch notes of legitimate chords belong to ONE pass and are
    # deliberately excluded. Only two different moving score copies can
    # generate the duplicate-note glitch described by the player.
    var heads: Array = []
    for item in passes:
        var floor: float = float(item["source_floor"])
        var ceiling: float = float(item["source_ceiling"])
        var origin: float = float(item["world_origin"])
        var identity: int = int(item["serial"])
        for raw in notes:
            var note: Dictionary = raw
            var source: float = float(note["beat"])
            if source < floor or source >= ceiling:
                continue
            var x: float = (origin+source-world)*pixels_per_beat
            if x < -tolerance_px or x > 1600.0+tolerance_px:
                continue
            heads.append({"serial":identity,"x":x,
                "pitch":int(note["pitch"])})
    var duplicates: Array = []
    for i in range(heads.size()):
        for j in range(i+1,heads.size()):
            if heads[i]["serial"] == heads[j]["serial"]:
                continue
            if heads[i]["pitch"] == heads[j]["pitch"] and \
                    absf(float(heads[i]["x"])-float(heads[j]["x"])) < tolerance_px:
                duplicates.append([heads[i],heads[j]])
    return duplicates

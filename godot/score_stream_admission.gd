extends RefCounted
## Single, forward-only source reservation contract. A Play/Resume action
## selects already pre-engraved, offscreen ink. It never creates a notehead
## at or ahead of the moving playhead by reconstructing the current source.
const MIN_READING_BEATS := 3.0
const OFFSCREEN_MARGIN_BEATS := 0.65
# A fresh READY reservation needs room to travel before it approaches the
# offscreen safety boundary. Without this slack, each frame immediately
# advances the boundary past the reservation and retimes it continuously.
const READY_TRAVEL_BEATS := 2.0
const REST_GAP_BEATS := 1.0

static func occupied_end(passes: Array, world: float) -> float:
    var last := -INF
    for item in passes:
        var finish: float = float(item["world_origin"]) + float(item["source_ceiling"])
        if finish > world:
            last = maxf(last,finish)
    return last

static func future_start(passes: Array, world: float,
        right_beats: float, header_beats: float) -> float:
    var start: float = world + maxf(MIN_READING_BEATS,
        right_beats + header_beats + OFFSCREEN_MARGIN_BEATS)
    var occupied: float = occupied_end(passes,world)
    if is_finite(occupied):
        start = maxf(start,occupied + REST_GAP_BEATS + header_beats)
    return start

static func pending_index(passes: Array, opening: float, world: float,
        right_beats: float = 0.0, header_beats: float = 0.0) -> int:
    # Visible ink begins before the first note at the real clef/key header.
    # A READY item with only 3 beats before its first note is not safe to
    # arm if its header has already scrolled into the viewport.
    var earliest: float = world + maxf(MIN_READING_BEATS,
        right_beats + header_beats + OFFSCREEN_MARGIN_BEATS)
    var chosen := -1
    var first_world := INF
    for index in range(passes.size()):
        var item: Dictionary = passes[index]
        var start: float = float(item["world_origin"]) + opening
        if not bool(item.get("pending",false)) or \
                str(item.get("take_key","prepared")) != "prepared" or \
                absf(float(item["source_floor"])-opening) > .00001 or \
                start < earliest or start >= first_world:
            continue
        chosen = index
        first_world = start
    return chosen

static func lead_seconds(start_world: float, world: float, bpm: float) -> float:
    return maxf(0.0,start_world-world)*60.0/maxf(1.0,bpm)

static func engraved_clip_bounds(floor: float, ceiling: float,
        pixels_per_beat: float, staff_gap: float,
        source_end: float = INF) -> Vector2:
    var leading := staff_gap*(15.0 if floor <= .0001 else 1.6)
    var trailing := staff_gap*2.2 if ceiling >= source_end-.0001 else 0.0
    return Vector2(floor*pixels_per_beat-leading,
        ceiling*pixels_per_beat+trailing)


static func paused_unplayed_index(passes: Array, take_key: String,
        opening: float, world: float) -> int:
    # A pause before the first graded note should reuse its already visible
    # (or still offscreen) source, rather than duplicate the same score.
    # Once any attack reached the playhead, the remaining passage needs
    # its own later-world reservation; old ink must continue drifting out.
    var best := -1
    var soonest := INF
    for index in range(passes.size()):
        var item: Dictionary = passes[index]
        if str(item.get("kind","source")) != "source" or \
                str(item.get("take_key","")) != take_key or \
                absf(float(item.get("source_floor",-INF))-opening) > .00001:
            continue
        var onset: float = float(item["world_origin"])+opening
        if onset < world+MIN_READING_BEATS or onset>=soonest:
            continue
        best=index
        soonest=onset
    return best


static func idle_reservation_index(passes: Array, opening: float) -> int:
    # One invisible, pre-engraved idle score is reused until Play. Retiming
    # this UNPUBLISHED reservation is safe; a sounding/armed score is never
    # moved. Avoid allocating a new CanvasItem every few idle seconds.
    for index in range(passes.size()):
        var item: Dictionary = passes[index]
        if str(item.get("kind","source")) == "source" and \
                str(item.get("take_key","")) == "prepared" and \
                bool(item.get("pending",false)) and \
                not bool(item.get("armed",false)) and \
                absf(float(item.get("source_floor",-INF))-opening) < .00001:
            return index
    return -1

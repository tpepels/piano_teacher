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

static func clip_bounds(item: Dictionary, density: float,
        gap: float, score_duration: float) -> Vector2:
    # The EXACT printed ink extent is shared by placement, projection and
    # retirement. Source and rest differ only in geometry data, not policy.
    if str(item.get("kind","source")) == "rest":
        return Vector2(0.0,float(item["source_ceiling"])*density)
    # Measure-sized immutable source strips partition a single engraved
    # passage. Exactly adjoining clip cuts share one printed world axis,
    # so even a beam crossing a boundary is neither duplicated nor lost.
    if item.has("clip_floor") and item.has("clip_ceiling"):
        return Vector2(float(item["clip_floor"])*density,
            float(item["clip_ceiling"])*density)
    return engraved_clip_bounds(
        float(item["source_floor"]),float(item["source_ceiling"]),
        density,gap,score_duration)


static func _occupied_end(passes: Array, world: float,
        density: float, gap: float, score_duration: float) -> float:
    var last := -INF
    for item in passes:
        var bounds: Vector2 = clip_bounds(
            item,density,gap,score_duration)
        var finish: float = float(item["world_origin"]) + bounds.y/density
        if finish > world:
            last = maxf(last,finish)
    return last


static func _future_start(passes: Array, world: float,
        right_beats: float, header_beats: float,
        density: float, gap: float, score_duration: float) -> float:
    var start: float = world + maxf(MIN_READING_BEATS,
        right_beats + header_beats + OFFSCREEN_MARGIN_BEATS)
    var occupied: float = _occupied_end(
        passes,world,density,gap,score_duration)
    if is_finite(occupied):
        start = maxf(start,occupied + REST_GAP_BEATS + header_beats)
    return start

# All reservation claims (ready, paused, automatic, active and auto due)
# use one identity-checked traversal. Type-specific callers must not scan
# stream_passes or calculate a different on-screen placement policy.
static func select(passes: Array, purpose: String, opening: float,
        world: float, right_beats: float = 0.0,
        header_beats: float = 0.0, identity: String = "",
        expected_world: float = NAN) -> int:
    assert(purpose in ["ready","idle","paused","automatic","automatic_due","bound"])
    var earliest: float = world + maxf(MIN_READING_BEATS,
        right_beats+header_beats+OFFSCREEN_MARGIN_BEATS)
    if purpose == "paused":
        earliest = world+MIN_READING_BEATS
    var chosen := -1
    var closest := -INF if purpose == "bound" else INF
    for index in range(passes.size()):
        var item: Dictionary = passes[index]
        if str(item.get("kind","source")) != "source":
            continue
        var key: String = str(item.get("take_key",""))
        var pending: bool = bool(item.get("pending",false))
        var armed: bool = bool(item.get("armed",false))
        var onset: float = float(item.get("world_origin",INF))+opening
        var matches: bool = false
        match purpose:
            "ready","idle":
                matches = pending and not armed and key == "prepared" and \
                    absf(float(item.get("source_floor",-INF))-opening)<.00001
            "paused":
                matches = key == identity and not pending and \
                    absf(float(item.get("source_floor",-INF))-opening)<.00001
            "automatic","automatic_due":
                matches = pending and not armed and key == "autopending" and \
                    absf(float(item.get("source_floor",-INF))-opening)<.00001
            "bound":
                matches = key == identity and not pending
        if not matches:
            continue
        if purpose not in ["idle","bound","automatic_due"] and \
                onset < earliest-.00001:
            continue
        if purpose == "automatic_due" and (not is_finite(expected_world) or \
                absf(onset-expected_world)>.75):
            continue
        # Active transport resumes may have two different source windows
        # attached to the same transport ID. Prefer the newest continuation;
        # other purposes always select the earliest future reservation.
        if (purpose == "bound" and onset > closest) or \
                (purpose != "bound" and onset < closest):
            closest = onset
            chosen = index
    return chosen


static func position(passes: Array, world: float, right_beats: float,
        header_beats: float, intended: float = NAN,
        travel_beats: float = 0.0, density: float = 96.0,
        gap: float = 24.0, score_duration: float = INF) -> float:
    # One common append-only boundary. No existing passage is ever excluded
    # or retimed to make a replacement appear earlier.
    var minimum: float = _future_start(
        passes,world,right_beats,header_beats,
        maxf(1.0,density),gap,score_duration)+travel_beats
    if is_finite(intended):
        return intended if intended >= minimum-.0001 else NAN
    return minimum


static func automatic_horizon(rest_beats: float,
        right_beats: float, header_beats: float) -> float:
    # This precise value is passed to the backend at Start AND used to place
    # speculative automatic/preview ink. The backend's repeat deadline
    # already includes the printed rest, so it adds only (horizon-rest).
    # Never push a visual repeat later without moving the grading deadline.
    return maxf(4.0,maxf(
        right_beats+header_beats+1.5,
        rest_beats+REST_GAP_BEATS+header_beats))


static func lead_seconds(start_world: float, world: float, bpm: float) -> float:
    return maxf(0.0,start_world-world)*60.0/maxf(1.0,bpm)

static func engraved_clip_bounds(floor: float, ceiling: float,
        pixels_per_beat: float, staff_gap: float,
        source_end: float = INF) -> Vector2:
    var leading := staff_gap*(15.0 if floor <= .0001 else 1.6)
    var trailing := staff_gap*2.2 if ceiling >= source_end-.0001 else 0.0
    return Vector2(floor*pixels_per_beat-leading,
        ceiling*pixels_per_beat+trailing)

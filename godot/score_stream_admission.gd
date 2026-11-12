extends RefCounted
## Single, forward-only source reservation contract. A Play/Resume action
## selects already pre-engraved, offscreen ink, or, on an empty strip, opens
## one count-in bar ahead of the playhead (empty_strip_start). It never pops
## a notehead in over, or ahead of, ink that is already visible.
const MIN_READING_BEATS := 3.0
# Keep the first printed pixel just beyond the viewport. Large margins
# multiply into seconds of blank screen at slow practice tempos.
const OFFSCREEN_MARGIN_BEATS := 0.12
# The reserved source remains strictly offscreen. The earlier 2-beat
# READY slack plus 0.65-beat margin added over five seconds of blank
# travel at 31 BPM before even the first printed clef entered the view.
# Use a short admission cushion; committed world origins never change.
const READY_TRAVEL_BEATS := 0.30
const REST_GAP_BEATS := 1.0
# "Strictly ahead of the playhead" for reusing a paused take.
const PAUSED_REUSE_EPSILON_BEATS := .001
# Listen/Perform may open on an empty strip only when the one-count-in-bar
# slot computed here (empty_strip_start) matches the engine's first-note
# deadline to within this many beats: one display frame of clock jitter,
# never a fraction of a note (0.025 beat is 2.4 px at 96 px/beat). It is not
# used for automatic practice continuations, which are bound by their
# backend plan identity (NativeView._planned_owner), not by comparing onsets.
const EMPTY_STRIP_DEADLINE_EPSILON_BEATS := .025

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
        return Vector2(
            float(item["clip_floor"])*density -
                float(item.get("clip_leading_spaces",0.0))*gap,
            float(item["clip_ceiling"])*density +
                float(item.get("clip_trailing_spaces",0.0))*gap)
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

# All reservation claims (ready, paused, automatic and active) use one
# identity-checked traversal. Type-specific callers must not scan
# stream_passes or calculate a different on-screen placement policy.
static func select(passes: Array, purpose: String, opening: float,
        world: float, right_beats: float = 0.0,
        header_beats: float = 0.0, identity: String = "") -> int:
    assert(purpose in ["ready","idle","paused","automatic","bound"])
    var earliest: float = world + maxf(MIN_READING_BEATS,
        right_beats+header_beats+OFFSCREEN_MARGIN_BEATS)
    if purpose == "paused":
        # A paused take's immutable ink is already placed; reusing it pops
        # nothing in. It only has to be strictly ahead of the playhead. A
        # reading floor here stranded Pause-in-count-in -> Resume behind an
        # offscreen append once the opening is one count-in bar ahead
        # (Task 2b review, owner decision 2026-11-08).
        earliest = world + PAUSED_REUSE_EPSILON_BEATS
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
            "automatic":
                matches = pending and not armed and key == "autopending" and \
                    absf(float(item.get("source_floor",-INF))-opening)<.00001
            "bound":
                matches = key == identity and not pending
        if not matches:
            continue
        if purpose not in ["idle","bound"] and \
                onset < earliest-.00001:
            continue
        # Active transport resumes may have two different source windows
        # attached to the same transport ID. Prefer the newest continuation;
        # other purposes always select the earliest future reservation.
        if (purpose == "bound" and onset > closest) or \
                (purpose != "bound" and onset < closest):
            closest = onset
            chosen = index
    return chosen


static func ink_ahead_of(passes: Array, world: float, density: float,
        gap: float, score_duration: float, except_take: int = -1) -> bool:
    # True when any printed SOURCE pixel lies right of the playhead. A
    # written rest bar between takes is printed silence: the next opening
    # may follow it on the staff (owner decision, round 4).
    for item in passes:
        if str(item.get("kind","source")) == "rest":
            continue
        if except_take >= 0 and int(item.get("take_owner",
                item.get("owner_serial",-1))) == except_take:
            continue
        # A source strip blocks while its MUSIC is ahead; its final barline
        # margin is only whitespace, which placement (empty_strip_start)
        # still clears. A take whose rest gap is shorter than that margin
        # (a passage ending mid-measure) otherwise kept "ink ahead" until
        # its one-bar slot had passed (Chopin 12/8, round 4).
        var music_end: float = float(item.get("clip_ceiling",
            item.get("source_ceiling",INF)))
        if not item.has("clip_ceiling") and not item.has("source_ceiling"):
            var bounds: Vector2 = clip_bounds(item,density,gap,score_duration)
            music_end = bounds.y/density
        if float(item["world_origin"]) + music_end > world+.00001:
            return true
    return false


static func empty_strip_start(passes: Array, world: float,
        count_in_beats: float, header_beats: float, peer_floor: float,
        density: float = 96.0, gap: float = 24.0,
        score_duration: float = INF, peer_rest_floor: float = NAN) -> float:
    # Owner decision 2026-11-08: "the notes should appear closer to the
    # playhead, so the wait is about one bar". With nothing printed right of
    # the playhead (this queue and every live peer layer), Play places the
    # opening's first source beat exactly one count-in bar ahead, so the
    # opening appears on the empty strip instead of travelling in from the
    # right edge. Otherwise NAN: the append-only offscreen rule applies.
    # Older ink that already passed the playhead keeps the same rest gap as
    # any appended passage; committed origins are never moved. A written
    # rest bar (owner decision, round 4) may still be ahead: the opening
    # then follows it directly, its header right after the rest's barline,
    # and its count-in is spoken over the rest bar. peer_floor (source ink
    # of a live peer layer) blocks; peer_rest_floor (a peer's written rest)
    # only positions the opening after it.
    if not is_finite(count_in_beats) or count_in_beats <= 0.0:
        return NAN
    density = maxf(1.0,density)
    if ink_ahead_of(passes,world,density,gap,score_duration):
        return NAN
    if is_finite(peer_floor) and peer_floor > world+.00001:
        return NAN
    var start: float = world + count_in_beats
    var last := -INF
    var last_is_rest := false
    for item in passes:
        var bounds: Vector2 = clip_bounds(item,density,gap,score_duration)
        var finish: float = float(item["world_origin"]) + bounds.y/density
        if finish > last:
            last = finish
            last_is_rest = str(item.get("kind","source")) == "rest"
    if is_finite(last):
        start = maxf(start,last + header_beats +
            (0.0 if last_is_rest else REST_GAP_BEATS))
    if is_finite(peer_floor):
        start = maxf(start,peer_floor + REST_GAP_BEATS + header_beats)
    if is_finite(peer_rest_floor):
        start = maxf(start,peer_rest_floor + header_beats)
    return start


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


static func retry_start(passes: Array, world: float, right_beats: float,
        header_beats: float, rest_beats: float, density: float = 96.0,
        gap: float = 24.0, score_duration: float = INF) -> float:
    # Owner, round 4 (item 7): a Retry opens at the right edge at once. Its
    # first printed pixel is just beyond the viewport and directly after
    # the ink already exposed (no REST_GAP, no READY travel), and never
    # closer than the one written rest measure the engine traverses first.
    var start: float = world + maxf(maxf(MIN_READING_BEATS,rest_beats),
        right_beats + header_beats + OFFSCREEN_MARGIN_BEATS)
    var occupied: float = _occupied_end(passes,world,maxf(1.0,density),gap,
        score_duration)
    if is_finite(occupied):
        start = maxf(start,occupied + header_beats)
    return start


static func automatic_horizon(rest_beats: float,
        right_beats: float, header_beats: float) -> float:
    # This precise value is passed to the backend at Start AND used to place
    # speculative automatic/preview ink. The backend's repeat deadline
    # already includes the printed rest, so it adds only (horizon-rest).
    # Never push a visual repeat later without moving the grading deadline.
    # The repeat is announced as the take ends, so it must clear the
    # printed rest by the same offscreen margin as any appended source:
    # with no margin the deadline sat exactly on the admission boundary and
    # a sub-millisecond projection error refused the repeat's ink.
    return maxf(4.0,maxf(
        right_beats+header_beats+1.5,
        rest_beats+REST_GAP_BEATS+header_beats+OFFSCREEN_MARGIN_BEATS))


static func command_lead_bpm(action: String, flow_bpm: float,
        selected_bpm: float) -> float:
    # World beats to seconds at the rate the axis moves at AFTER a command:
    # Play's count-in and Retry's rest run at the selected BPM (a tempo-
    # mapped take, e.g. a slowdown stage, ran at its own rate until now); a
    # mid-take Resume continues inside the take's map.
    return flow_bpm if action == "resume" else selected_bpm


static func lead_seconds(start_world: float, world: float, bpm: float) -> float:
    return maxf(0.0,start_world-world)*60.0/maxf(1.0,bpm)

static func engraved_clip_bounds(floor: float, ceiling: float,
        pixels_per_beat: float, staff_gap: float,
        source_end: float = INF) -> Vector2:
    var leading := staff_gap*(15.0 if floor <= .0001 else 1.6)
    var trailing := staff_gap*2.2 if ceiling >= source_end-.0001 else 0.0
    return Vector2(floor*pixels_per_beat-leading,
        ceiling*pixels_per_beat+trailing)

extends RefCounted
## One pure preflight for every user-triggered Play/Resume/Retry.
## All source geometry, queue exposure and peer-layer accounting live in
## existing authoritative ScoreStreamAdmission / ScoreStreamQueue contracts.
## This class cannot create, move, arm, or remove CanvasItems.
const Admission := preload("res://score_stream_admission.gd")

static func _refuse(reason: String) -> Dictionary:
    return {"ok":false,"reason":reason}

static func plan(renderer, action: String, world: float,
        source_opening: float, count_in_beats: float) -> Dictionary:
    # count_in_beats is the engine's published next_count_in_beats: the one
    # count-in bar this Play/Resume gets before its first source beat.
    if action not in ["start","resume","restart"]:
        return _refuse("unsupported_action")
    if not is_finite(world) or not is_finite(source_opening):
        return _refuse("invalid_transport_coordinate")
    if not bool(renderer.native_ready) or not renderer.retained_ready():
        return _refuse("notation_not_compiled")
    var duration: float = float(renderer.timeline.duration_beats)
    if duration <= 0.0 or source_opening < 0.0 or             source_opening >= duration:
        return _refuse("invalid_source_interval")
    # Every caller, including isolated production fixtures, must provide
    # the identical identity-bound frozen preflight model. No code path
    # may read a renderer's mutable private queue or recalculate placement.
    if not renderer.has_method("transport_preflight_facts"):
        return _refuse("missing_physical_preflight_port")
    var facts: Dictionary = renderer.transport_preflight_facts(
        world,source_opening)
    for field in ["source_exists","online","right","header",
            "preview_world","withdrawn","peer_floor"]:
        if not facts.has(field):
            return _refuse("incomplete_physical_preflight_facts")
    if not bool(facts["source_exists"]):
        return _refuse("no_source_measures")
    var density: float = float(renderer.timeline.pixels_per_beat)
    var staff_gap: float = float(renderer.staff_gap())
    var width: float = float(renderer.size.x)
    if density <= 0.0 or staff_gap <= 0.0 or width < 100.0:
        return _refuse("score_viewport_not_ready")
    var online: Array = facts["online"]
    var right: float = float(facts["right"])
    var header: float = float(facts["header"])
    var preview_world: float = float(facts["preview_world"])
    var withdrawn: Dictionary = facts["withdrawn"]
    if not withdrawn.has("remaining") or not withdrawn.has("owners"):
        return _refuse("incomplete_physical_preflight_facts")
    var survivors: Array = withdrawn["remaining"]
    var peer_floor: float = float(facts["peer_floor"])
    var was_paused: bool = bool(facts.get("was_paused",false))
    var paused_source: float = float(facts.get("paused_source",0.0))
    var paused_owner: int = int(facts.get("paused_owner",-1))
    var last_take: String = str(facts.get("last_take",""))
    # Owner decision 2026-11-08: Play or Resume on an empty strip opens one
    # count-in bar ahead of the playhead. A hidden READY take was never
    # seen, so it is withdrawn rather than reused from beyond the right edge.
    var near_onset: float = NAN
    if action in ["start","resume"]:
        near_onset = Admission.empty_strip_start(survivors,preview_world,
            count_in_beats,header,peer_floor,density,staff_gap,duration)
    # A prepared, fully offscreen take is the cheapest valid reservation
    # while other ink is still moving ahead of the playhead.
    var reusable := -1
    if action == "start" and not is_finite(near_onset):
        reusable = Admission.select(online,"ready",
            source_opening,preview_world,right,header)
    elif action == "resume":
        if was_paused and absf(source_opening-paused_source) < .0001:
            reusable = Admission.select(online,"paused",
                source_opening,preview_world,0.0,0.0,
                last_take)
            if reusable < 0 and paused_owner >= 0:
                # A Pause snapshot can arrive before Play's ACK binds the
                # backend transport key. The provisional ARMED source is
                # still authoritative, and must not be retracted.
                for index in range(online.size()):
                    var item: Dictionary = online[index]
                    if str(item.get("kind","")) != "source" or \
                            int(item.get("take_owner",-1)) != \
                                paused_owner:
                        continue
                    var key: String = str(item.get("take_key",""))
                    var onset: float = float(item["world_origin"]) + source_opening
                    if key.begins_with("armed:") and \
                            absf(float(item.get("source_floor",-1))-
                                source_opening) < .00001 and \
                            onset >= preview_world+Admission.PAUSED_REUSE_EPSILON_BEATS:
                        reusable = index
                        break
        if reusable < 0:
            reusable = Admission.select(online,"automatic",
                source_opening,preview_world,right,header)
    if reusable >= 0 and float(online[reusable]["world_origin"]) + \
            source_opening < preview_world+count_in_beats-.0001:
        reusable = -1
    if reusable >= 0:
        return {"ok":true,"mode":"reuse","action":action,
            "opening":source_opening,
            "protected_take":int(online[reusable].get("take_owner",
                online[reusable]["serial"])),
            "start_world":float(online[reusable]["world_origin"]) +
                source_opening,"reason":"existing_future_owner"}
    if is_finite(near_onset):
        return {"ok":true,"mode":"append","action":action,
            "opening":source_opening,"start_world":near_onset,
            "empty_strip":true,
            "first_pixel_x":width*renderer.PLAYHEAD_FRACTION +
                (near_onset-header-preview_world)*density,
            "first_ink_delay_seconds":0.0,
            "remaining_count":survivors.size(),
            "withdraw_owners":withdrawn["owners"].duplicate(),
            "reason":"empty_strip_count_in_bar"}
    var onset: float = Admission.position(survivors,preview_world,
        right,header,NAN,Admission.READY_TRAVEL_BEATS,
        density,staff_gap,duration)
    if action == "restart":
        onset = Admission.retry_start(survivors,preview_world,right,header,
            float(renderer.practice_timeline.get("gap",{}).get(
                "duration_beats",0.0)),density,staff_gap,duration)
    if is_finite(peer_floor):
        onset = maxf(onset,peer_floor+header+Admission.REST_GAP_BEATS)
    if is_finite(count_in_beats) and count_in_beats > 0.0:
        # The engine counts one whole bar before grading starts. The slot
        # must be at least that far ahead, or grading (count-in bar) and
        # ink (shorter offscreen slot) would be two deadlines. With no
        # written rest between takes the offscreen slot can be shorter.
        onset = maxf(onset,preview_world+count_in_beats)
    if not is_finite(onset):
        return _refuse("no_finite_future_slot")
    var first_pixel_x: float = width*renderer.PLAYHEAD_FRACTION +         (onset-header-preview_world)*density
    if first_pixel_x <= width:
        return _refuse("not_fully_offscreen")
    return {"ok":true,"mode":"append","action":action,
        "opening":source_opening,"start_world":onset,"empty_strip":false,
        "first_pixel_x":first_pixel_x,
        "first_ink_delay_seconds":
            Admission.lead_seconds(maxf(0.0,(first_pixel_x-width)/density),0.0,
                maxf(1.0,float(renderer.bpm))),
        "remaining_count":survivors.size(),
        "withdraw_owners":withdrawn["owners"].duplicate(),
        "reason":"new_immutable_future_slot"}

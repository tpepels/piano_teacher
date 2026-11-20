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
    if not renderer.has_method("transport_preflight_facts"):
        return _refuse("missing_physical_preflight_port")
    var facts: Dictionary = renderer.transport_preflight_facts(world,source_opening)
    return plan_facts(facts,action,world,source_opening,count_in_beats)

static func plan_facts(facts: Dictionary, action: String, world: float,
        source_opening: float, count_in_beats: float,
        exact_start_world: float = NAN) -> Dictionary:
    if action not in ["start","resume","restart","auto"]:
        return _refuse("unsupported_action")
    if not is_finite(world) or not is_finite(source_opening):
        return _refuse("invalid_transport_coordinate")
    if not bool(facts.get("ready",false)):
        return _refuse("notation_not_compiled")
    var duration: float = float(facts.get("duration",0.0))
    if duration <= 0.0 or source_opening < 0.0 or source_opening >= duration:
        return _refuse("invalid_source_interval")
    for field in ["source_exists","online","right","header",
            "preview_world","withdrawn","peer_floor"]:
        if not facts.has(field):
            return _refuse("incomplete_physical_preflight_facts")
    if not bool(facts["source_exists"]):
        return _refuse("no_source_measures")
    var density: float = float(facts["density"])
    var staff_gap: float = float(facts["gap"])
    var width: float = float(facts["width"])
    if density <= 0.0 or staff_gap <= 0.0 or width < 100.0:
        return _refuse("score_viewport_not_ready")
    var online: Array = facts["online"]
    var right: float = float(facts["right"])
    var header: float = float(facts["header"])
    var preview_world: float = float(facts["preview_world"])
    var withdrawn: Dictionary = facts["withdrawn"]
    var protected_strip := -1
    if action == "resume" and facts.has("resume_protected_strip"):
        protected_strip = int(facts["resume_protected_strip"])
        if not facts.has("resume_withdrawn"):
            return _refuse("missing_paused_source_withdrawal_preview")
        withdrawn = facts["resume_withdrawn"]
    if not withdrawn.has("remaining") or not withdrawn.has("owners"):
        return _refuse("incomplete_physical_preflight_facts")
    var survivors: Array = withdrawn["remaining"]
    var peer_floor: float = float(facts["peer_floor"])
    if action == "auto":
        # The backend's direct repeat already began its one count-in bar at
        # the preceding sounding end. Physical admission may consume that
        # lead; it cannot choose a second musical deadline or extra runway.
        if not is_finite(exact_start_world) or exact_start_world <= world:
            return _refuse("expired_direct_repeat")
        if not facts.has("peer_source_floor"):
            return _refuse("missing_direct_repeat_peer_clearance")
        var incoming_left: float = exact_start_world-header
        for item in survivors:
            if str(item.get("kind","source")) != "source":
                continue
            var ink: Vector2 = Admission.clip_bounds(item,density,staff_gap,duration)
            var ink_right: float = float(item["world_origin"])+ink.y/density
            if ink_right > incoming_left+.0001:
                return _refuse("direct_repeat_overlaps_exposed_source")
        var peer_source: float = float(facts["peer_source_floor"])
        if is_finite(peer_source) and peer_source > incoming_left+.0001:
            return _refuse("direct_repeat_overlaps_peer_source")
        return {"ok":true,"mode":"append","action":action,
            "opening":source_opening,"start_world":exact_start_world,
            "empty_strip":false,"remaining_count":survivors.size(),
            "withdraw_owners":withdrawn["owners"].duplicate(),
            "reason":"authoritative_one_bar_repeat"}
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
    if action == "start" and not is_finite(near_onset) and \
            not bool(facts.get("display_context_required",false)):
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
            "first_pixel_x":float(facts["playhead"]) +
                (near_onset-header-preview_world)*density,
            "first_ink_delay_seconds":0.0,
            "remaining_count":survivors.size(),
            "protected_strip":protected_strip,
            "withdraw_owners":withdrawn["owners"].duplicate(),
            "reason":"empty_strip_count_in_bar"}
    var onset: float = Admission.position(survivors,preview_world,
        right,header,NAN,Admission.READY_TRAVEL_BEATS,
        density,staff_gap,duration)
    var leading_rest := 0.0
    if action == "restart":
        # Withdrawing an entirely unseen take also withdraws its paired
        # rest. The replacement must then own the written preparation bar;
        # silence before its first note is not itself a printed rest.
        leading_rest = float(facts["rest_gap"])
        for item in survivors:
            if str(item.get("kind","")) == "rest" and \
                    float(item.get("world_origin",-INF)) >= preview_world-.0001 and \
                    float(item.get("source_ceiling",0.0)) >= leading_rest-.0001:
                leading_rest = 0.0
                break
        onset = Admission.retry_start(survivors,preview_world,right,header,
            float(facts["rest_gap"]),density,staff_gap,duration,leading_rest)
    if is_finite(peer_floor):
        onset = maxf(onset,peer_floor+header+
            maxf(Admission.REST_GAP_BEATS,leading_rest))
    if is_finite(count_in_beats) and count_in_beats > 0.0:
        # The engine counts one whole bar before grading starts. The slot
        # must be at least that far ahead, or grading (count-in bar) and
        # ink (shorter offscreen slot) would be two deadlines. With no
        # written rest between takes the offscreen slot can be shorter.
        onset = maxf(onset,preview_world+count_in_beats)
    if not is_finite(onset):
        return _refuse("no_finite_future_slot")
    var first_pixel_x: float = float(facts["playhead"]) +         (onset-header-preview_world)*density
    if first_pixel_x <= width:
        return _refuse("not_fully_offscreen")
    return {"ok":true,"mode":"append","action":action,
        "opening":source_opening,"start_world":onset,"empty_strip":false,
        "first_pixel_x":first_pixel_x,
        "first_ink_delay_seconds":
            Admission.lead_seconds(maxf(0.0,(first_pixel_x-width)/density),0.0,
                maxf(1.0,float(facts["bpm"]))),
        "remaining_count":survivors.size(),
        "protected_strip":protected_strip,
        "leading_rest_beats":leading_rest,
        "withdraw_owners":withdrawn["owners"].duplicate(),
        "reason":"new_immutable_future_slot"}
